"""Stage official portable releases alongside the running Windows application."""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import ntpath
import os
from pathlib import Path
import re
import shutil
import ssl
import stat
import subprocess
import sys
import tempfile
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, HTTPSHandler, Request
from zipfile import BadZipFile, ZipFile, ZIP_DEFLATED, ZIP_STORED

REPOSITORY_URL = 'https://github.com/payuktv/director-calendar'
APP = 'DirectorCalendar.exe'
CACHE = '.director-updates'
OWNER = b'Director Calendar update cache v1\n'
MAX_DOWNLOAD = 256 * 1024 * 1024
MAX_EXPANDED = 768 * 1024 * 1024
MAX_ENTRIES = 8192
BLOCK = 256 * 1024
MAX_SECONDS = 900
_VERSION = re.compile(r'(?:0|[1-9][0-9]{0,8})(?:\.(?:0|[1-9][0-9]{0,8})){2}')
_HASH = re.compile(r'[a-f0-9]{64}')


def version_key(value):
    if not isinstance(value, str) or not _VERSION.fullmatch(value):
        raise ValueError('Invalid release version')
    return tuple(map(int, value.split('.')))


@dataclass(frozen=True)
class Package:
    version: str
    size: int
    sha256: str

    def __post_init__(self):
        version_key(self.version)
        if type(self.size) is not int or not 0 < self.size <= MAX_DOWNLOAD:
            raise ValueError('Invalid package size')
        if not isinstance(self.sha256, str) or not _HASH.fullmatch(self.sha256):
            raise ValueError('Invalid package digest')

    @property
    def name(self):
        return f'DirectorCalendar-{self.version}-portable-x64.zip'

    @property
    def url(self):
        return f'{REPOSITORY_URL}/releases/download/v{self.version}/{self.name}'


def packaged():
    return sys.platform == 'win32' and bool(getattr(sys, 'frozen', False))


def install_root(executable):
    folder = Path(executable).absolute().parent
    if folder.parent.name == CACHE and folder.name.startswith('v') and _VERSION.fullmatch(folder.name[1:]):
        return folder.parent.parent
    return folder


def _linked(path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & 0x400)


def _plain_path(path):
    return not any(_linked(part) for part in (path, *path.parents))


def _small_bytes(path, limit):
    if _linked(path) or not path.is_file():
        return b''
    with path.open('rb') as stream:
        return stream.read(limit + 1)


def _cache(root, create=False):
    cache = root / CACHE
    if not _plain_path(cache):
        raise ValueError('Linked update directory')
    if create:
        try:
            cache.mkdir()
        except FileExistsError:
            pass
        else:
            (cache / '.owner').write_bytes(OWNER)
    if _small_bytes(cache / '.owner', len(OWNER)) != OWNER:
        raise ValueError('Unrecognized update directory')
    return cache


def _ready(folder, version):
    if _linked(folder) or not folder.is_dir():
        return False
    receipt = _small_bytes(folder / '.ready', 64)
    return (len(receipt) == 64 and re.fullmatch(b'[a-f0-9]{64}', receipt) is not None
            and _small_bytes(folder / 'version.txt', 40).strip() == version.encode('ascii')
            and not _linked(folder / APP) and (folder / APP).is_file()
            and not _linked(folder / '_internal') and (folder / '_internal').is_dir())


def ready_target(root, current):
    """Only committed, newer versions are eligible, even after interrupted staging."""
    current_key = version_key(current)
    try:
        cache = _cache(root)
        slots = [(version_key(p.name[1:]), p) for p in cache.iterdir()
                 if p.name.startswith('v') and _VERSION.fullmatch(p.name[1:])]
        for key, folder in sorted(slots, reverse=True):
            if key <= current_key:
                break
            if _ready(folder, folder.name[1:]):
                return folder / APP
    except (OSError, ValueError):
        pass
    return None


def launch_ready(executable, current, *, environ=None):
    target = ready_target(install_root(executable), current)
    if target is None:
        return None
    # A fresh PyInstaller runtime must use the new package's libraries.
    env = dict(os.environ if environ is None else environ, PYINSTALLER_RESET_ENVIRONMENT='1')
    return subprocess.Popen([str(target)], cwd=target.parent, env=env, close_fds=True)


def probe_package(staging, version):
    result = subprocess.run([str(staging / APP), '--verify-update-version', version], cwd=staging,
                            env=dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT='1'),
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
    if result.returncode:
        raise ValueError('The staged application failed its startup check')


class _AssetRedirect(HTTPRedirectHandler):
    max_redirections = 4

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urlsplit(newurl)
        if (target.scheme != 'https' or target.netloc not in
                {'release-assets.githubusercontent.com', 'objects.githubusercontent.com'} or target.fragment):
            raise ValueError('Unexpected asset redirect')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def open_package(package):
    import certifi
    tls = ssl.create_default_context()
    tls.load_verify_locations(cafile=certifi.where())
    opener = build_opener(_AssetRedirect(), HTTPSHandler(context=tls))
    request = Request(package.url, headers={'User-Agent': 'DirectorCalendar-Update', 'Accept-Encoding': 'identity'})
    return opener.open(request, timeout=15)


def _member_parts(name):
    pieces = name.replace('\\', '/').removesuffix('/').split('/')
    if (len(pieces) > 32 or len(name) > 600 or any(not p or p in {'.', '..'} or ntpath.isreserved(p)
                                                 or p.endswith(('.', ' ')) or len(p) > 255 for p in pieces)):
        raise ValueError('Invalid package path')
    return pieces


def _payload_path(parts):
    return parts in ([APP], ['version.txt']) or bool(parts and parts[0] == '_internal')


def _unpack(archive, staging, version):
    files, seen = [], set()
    with ZipFile(archive) as source:
        entries = source.infolist()
        if len(entries) > MAX_ENTRIES or sum(entry.file_size for entry in entries) > MAX_EXPANDED:
            raise ValueError('Package exceeds extraction limits')
        for entry in entries:
            name = entry.orig_filename
            parts = _member_parts(name)
            mode = stat.S_IFMT(entry.external_attr >> 16)
            if (parts[0] != 'DirectorCalendar' or (len(parts) > 1 and not _payload_path(parts[1:]))
                    or mode not in (0, stat.S_IFDIR, stat.S_IFREG) or entry.external_attr & 0x400
                    or entry.flag_bits & 1 or entry.compress_type not in (ZIP_STORED, ZIP_DEFLATED)):
                raise ValueError('Unexpected package member')
            key = '/'.join(parts).casefold()
            if key in seen:
                raise ValueError('Duplicate package path')
            seen.add(key)
            path = staging.joinpath(*parts[1:])
            if name.endswith(('/', '\\')):
                path.mkdir(parents=True, exist_ok=True)
                continue
            if len(parts) < 2:
                raise ValueError('Missing package directory')
            path.parent.mkdir(parents=True, exist_ok=True)
            with source.open(entry) as src, path.open('xb') as dest:
                shutil.copyfileobj(src, dest, BLOCK)
            files.append('/'.join(parts[1:]))
    if (APP not in files or not any(f.startswith('_internal/') for f in files)
            or _small_bytes(staging / 'version.txt', 40).strip() != version.encode('ascii')):
        raise ValueError('Incomplete package or wrong version')
    (staging / '.files').write_text('\n'.join(files) + '\n', encoding='utf-8-sig')


def _clear_slot(folder):
    """Remove only recorded payload files. Keep additions in an extracted copy."""
    version = folder.name[1:]
    if not _VERSION.fullmatch(version) or not _ready(folder, version):
        return
    receipt = _small_bytes(folder / '.files', MAX_ENTRIES * 610)
    if not receipt or len(receipt) > MAX_ENTRIES * 610:
        return
    names = receipt.decode('utf-8-sig').splitlines()
    parts = [_member_parts(name) for name in names]
    if [APP] not in parts or len(parts) > MAX_ENTRIES or not all(_payload_path(p) for p in parts):
        return
    # Windows refuses to unlink an executable in use by any running profile.
    # Check that before removing libraries it may still need.
    (folder / APP).unlink()
    dirs = set()
    for p in parts:
        path = folder.joinpath(*p)
        if _plain_path(path):
            path.unlink(missing_ok=True)
            dirs.update(parent for parent in path.parents if folder in parent.parents)
    for marker in ('.files', '.ready'):
        (folder / marker).unlink(missing_ok=True)
    for directory in sorted(dirs, key=lambda p: len(p.parts), reverse=True):
        if _plain_path(directory):
            _remove_empty(directory)
    _remove_empty(folder)


def _remove_empty(path):
    try:
        path.rmdir()
    except OSError:
        pass


def _remove_work(cache, work):
    # Only a private staging directory directly under this installation's cache.
    if (work.parent != cache or work.resolve().parent != cache.resolve() or not _plain_path(work)
            or not work.name.startswith('stage-') or _small_bytes(work / '.owner', len(OWNER)) != OWNER):
        return
    shutil.rmtree(work)


def _prune(cache, keep):
    for folder in cache.iterdir():
        try:
            if folder.name.startswith('stage-'):
                _remove_work(cache, folder)
            elif folder.name.startswith('v') and _VERSION.fullmatch(folder.name[1:]) and folder.name not in keep:
                _clear_slot(folder)
        except (OSError, ValueError):
            continue


@contextmanager
def _locked(cache):
    from PySide6.QtCore import QLockFile
    if _linked(cache / '.lock'):
        raise ValueError('Invalid update lock path')
    lock = QLockFile(str(cache / '.lock'))
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        raise BlockingIOError('Another update is active')
    try:
        yield
    finally:
        lock.unlock()


def prepare_package(executable, current, package, *, open_asset=open_package, probe=probe_package, progress=None):
    if version_key(package.version) <= version_key(current):
        raise ValueError('Update must be newer')
    root = install_root(executable)
    cache = _cache(root, create=True)
    slot = cache / ('v' + package.version)
    with _locked(cache):
        ready = ready_target(root, current)
        if ready and version_key(ready.parent.name[1:]) >= version_key(package.version):
            return ready
        if slot.exists() or _linked(slot):
            raise ValueError('Update destination is occupied')
        keep = {'v' + current}
        if ready:
            keep.add(ready.parent.name)
        _prune(cache, keep)
        with tempfile.TemporaryDirectory(prefix='stage-', dir=cache) as temporary:
            work = Path(temporary)
            (work / '.owner').write_bytes(OWNER)
            archive = work / 'release.zip'
            start, size, sha = monotonic(), 0, hashlib.sha256()
            last_percent = -1
            with open_asset(package) as response, archive.open('xb') as output:
                if response.status != 200:
                    raise ValueError('Incomplete HTTP response')
                while chunk := response.read1(BLOCK):
                    if monotonic() - start > MAX_SECONDS:
                        raise TimeoutError('Update timed out')
                    size += len(chunk)
                    if size > package.size:
                        raise ValueError('Package is larger than declared')
                    sha.update(chunk)
                    output.write(chunk)
                    percent = size * 100 // package.size
                    if progress is not None and percent != last_percent:
                        progress(percent)
                        last_percent = percent
            if size != package.size or sha.hexdigest() != package.sha256:
                raise ValueError('Package verification failed')
            staging = work / 'payload'
            staging.mkdir()
            _unpack(archive, staging, package.version)
            probe(staging, package.version)
            (staging / '.ready').write_bytes(package.sha256.encode('ascii'))
            # Both locations are within the same guarded cache and filesystem.
            if staging.resolve().parent != work.resolve() or slot.resolve().parent != cache.resolve():
                raise ValueError('Invalid promotion path')
            staging.rename(slot)
            return slot / APP


def worker_main(args):
    from . import __version__
    if not packaged() or len(args) != 3:
        return 2
    try:
        from .sync_process import pipe_stream
        output = pipe_stream(sys.stdout, -11, 'wb')
        def report(percent):
            output.write(f'{percent}\n'.encode('ascii'))
            output.flush()
        package = Package(args[0], int(args[1]), args[2])
        prepare_package(sys.executable, __version__, package, progress=report)
        return 0
    except (HTTPError, URLError, TimeoutError):
        return 3
    except (ValueError, BadZipFile):
        return 2
    except OSError:
        return 4
