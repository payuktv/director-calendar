"""Installer-free updates publish a fully verified directory or leave the old app in place."""
from dataclasses import replace
import hashlib
from io import BytesIO
from urllib.request import Request
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from director_control import package_update as updater
from director_control.desktop import shortcut_spec


class Response(BytesIO):
    status = 200


def bundle(version, extra=None, *, marker=None, separator='/'):
    data = BytesIO()
    with ZipFile(data, 'w', ZIP_DEFLATED) as archive:
        entries = {updater.APP: b'synthetic application', 'version.txt': (marker or version).encode(),
                   '_internal/components/нужный файл.txt': b'synthetic runtime'}
        for name, content in (entries | (extra or {})).items():
            archive.writestr(('DirectorCalendar/' + name).replace('/', separator), content)
    return data.getvalue()


def package(version, data):
    return updater.Package(version, len(data), hashlib.sha256(data).hexdigest())


def stage(exe, current, version, *, data=None, metadata=None, probe=lambda *_: None):
    data = data if data is not None else bundle(version)
    return updater.prepare_package(exe, current, metadata or package(version, data),
                                   open_asset=lambda p, offset: Response(data), probe=probe)


@pytest.fixture
def exe(tmp_path):
    folder = tmp_path / "Календарь O'Neil & тест"
    folder.mkdir()
    path = folder / updater.APP
    path.write_bytes(b'working bootstrap')
    return path


@pytest.mark.parametrize('separator', ['/', '\\'])
def test_shortcut_requires_confirmed_activation_after_complete_verification(exe, monkeypatch, separator):
    data = bundle('1.10.0', separator=separator)
    observations = []
    def probe(folder, version):
        assert (folder / updater.APP).read_bytes() == b'synthetic application'
        observations.append(updater.ready_target(exe.parent, '1.9.0'))
    target = stage(exe, '1.9.0', '1.10.0', data=data, probe=probe)
    assert observations == [None] and exe.read_bytes() == b'working bootstrap'
    assert updater.ready_target(exe.parent, '1.9.0') is None
    assert updater.pending_target(exe.parent, '1.9.0') == target
    assert updater.launch_ready(exe, '1.9.0') is None
    with pytest.raises(ValueError):
        updater.activate_package(exe, '1.9.0', '1.10.1')
    target = updater.activate_package(exe, '1.9.0', '1.10.0')
    assert updater.pending_target(exe.parent, '1.9.0') is None
    assert updater.ready_target(exe.parent, '1.9.0') == target
    assert updater.install_root(target) == exe.parent
    assert shortcut_spec(executable=target, frozen=True).target == exe
    with pytest.raises(ValueError):
        stage(exe, '1.10.0', '1.9.0')
    # Restart uses a fixed trusted program path and resets PyInstaller's runtime.
    calls = []
    monkeypatch.setattr(updater.subprocess, 'Popen', lambda args, **kw: calls.append((args, kw)) or 'child')
    assert updater.launch_ready(exe, '1.9.0') == 'child'
    assert calls[0][0] == [str(target)] and calls[0][1]['cwd'] == target.parent
    assert calls[0][1]['env']['PYINSTALLER_RESET_ENVIRONMENT'] == '1'
    assert updater.launch_ready(target, '1.10.0') is None


@pytest.mark.parametrize('failure', ['truncated', 'too large', 'wrong digest', 'wrong version', 'incomplete', 'probe'])
def test_bad_or_interrupted_package_cannot_displace_last_working_version(exe, failure, monkeypatch):
    monkeypatch.setattr(updater, 'sleep', lambda _: None)
    stage(exe, '1.3.0', '1.4.0')
    first = updater.activate_package(exe, '1.3.0', '1.4.0')
    good = bundle('1.5.0')
    data, meta = good, package('1.5.0', good)
    def probe(path, version):
        if failure == 'probe':
            raise ValueError('startup check failed')
    if failure == 'truncated':
        data = good[:-1]
    if failure == 'too large':
        meta = replace(meta, size=len(good)-1)
    if failure == 'wrong digest':
        meta = replace(meta, sha256='0'*64)
    if failure == 'wrong version':
        data = bundle('1.5.0', marker='1.4.0')
        meta = package('1.5.0', data)
    if failure == 'incomplete':
        empty = BytesIO()
        with ZipFile(empty, 'w') as archive:
            archive.writestr('DirectorCalendar/version.txt', '1.5.0')
        data = empty.getvalue()
        meta = package('1.5.0', data)
    with pytest.raises(ConnectionError if failure == 'truncated' else ValueError):
        stage(first, '1.4.0', '1.5.0', data=data, metadata=meta, probe=probe)
    assert updater.ready_target(exe.parent, '1.3.0') == first
    assert updater.ready_target(exe.parent, '1.4.0') is None
    assert updater.pending_target(exe.parent, '1.4.0') is None
    assert [p.name for p in (exe.parent / updater.CACHE).glob('stage-*')] == [updater.PENDING]


def test_retry_and_multiple_releases_prune_only_recorded_old_files(exe):
    stage(exe, '1.3.0', '1.4.0')
    first = updater.activate_package(exe, '1.3.0', '1.4.0')
    note = first.parent / '_internal/personal.txt'
    note.write_text('mine')
    second = stage(first, '1.4.0', '1.5.0')
    assert stage(first, '1.4.0', '1.5.0', probe=lambda *_: pytest.fail('duplicate')) == second
    second = updater.activate_package(first, '1.4.0', '1.5.0')
    stage(second, '1.5.0', '1.6.0')
    third = updater.activate_package(second, '1.5.0', '1.6.0')
    assert not first.exists() and note.read_text() == 'mine'
    assert second.is_file() and updater.ready_target(exe.parent, '1.3.0') == third
    assert exe.is_file()


def test_unrelated_existing_directory_is_never_adopted_or_cleaned(exe):
    cache = exe.parent / updater.CACHE
    cache.mkdir()
    note = cache / 'my file'
    note.write_text('mine')
    with pytest.raises(ValueError):
        stage(exe, '1.3.0', '1.4.0')
    assert list(cache.iterdir()) == [note]


def test_replacing_a_pending_package_never_activates_either_version(exe):
    first = stage(exe, '1.4.0', '1.4.1')
    broken = bundle('1.4.2', marker='1.4.1')
    with pytest.raises(ValueError):
        stage(exe, '1.4.0', '1.4.2', data=broken)
    assert updater.pending_target(exe.parent, '1.4.0') == first
    second = stage(exe, '1.4.0', '1.4.2')
    assert updater.pending_target(exe.parent, '1.4.0') == second and not first.exists()
    with pytest.raises(ValueError):
        updater.activate_package(exe, '1.4.0', '1.4.1')
    assert updater.launch_ready(exe, '1.4.0') is None
    assert updater.activate_package(exe, '1.4.0', '1.4.2').is_file()


@pytest.mark.parametrize('name', ['outside.txt', '_internal/../outside', '_internal/file:alternate',
                                  '_internal/NUL.txt', '_internal/empty./data', '_internal//ambiguous'])
def test_package_members_must_be_unambiguous_windows_payload_paths(exe, name):
    data = bundle('1.4.0', {name: b'invalid entry'})
    with pytest.raises(ValueError):
        stage(exe, '1.3.0', '1.4.0', data=data)
    assert updater.ready_target(exe.parent, '1.3.0') is None


def test_worker_only_accepts_official_github_https_asset_redirects():
    handler = updater._AssetRedirect()
    request = Request(package('1.4.0', b'x').url)
    target = 'https://release-assets.githubusercontent.com/example?signature=shortlived'
    redirected = handler.redirect_request(request, None, 302, '', {}, target)
    assert redirected.full_url == target
    for url in ('http://release-assets.githubusercontent.com/file', 'https://unknown.example/file',
                'https://github.com/other/product', 'https://user@objects.githubusercontent.com/file',
                'https://objects.githubusercontent.com:8443/file'):
        with pytest.raises(ValueError):
            handler.redirect_request(request, None, 302, '', {}, url)


@pytest.mark.parametrize('resume', ['partial', 'full', 'wrong range', 'altered bytes'])
def test_resumption_verifies_byte_range_and_complete_digest(exe, monkeypatch, resume):
    monkeypatch.setattr(updater, 'sleep', lambda _: None)
    data = bundle('1.4.0')
    meta = package('1.4.0', data)
    cut = 37
    offsets = []
    class Interrupted(Response):
        def read1(self, n):
            if self.tell() >= cut:
                raise TimeoutError('connection stalled')
            return super().read1(cut)
    def open_asset(pkg, offset):
        assert pkg == meta
        offsets.append(offset)
        if not offset:
            return Interrupted(data)
        if resume == 'full':
            return Response(data)
        result = Response(data[offset:] if resume != 'altered bytes' else bytes(len(data) - offset))
        result.status = 206
        begin = 0 if resume == 'wrong range' else offset
        result.headers = {'Content-Range': f'bytes {begin}-{len(data)-1}/{len(data)}'}
        return result
    def prepare():
        return updater.prepare_package(exe, '1.3.1', meta, open_asset=open_asset, probe=lambda *_: None)
    if resume in ('wrong range', 'altered bytes'):
        with pytest.raises(ValueError):
            prepare()
        assert updater.ready_target(exe.parent, '1.3.1') is None
    else:
        result = prepare()
        assert result == updater.pending_target(exe.parent, '1.3.1')
        assert updater.ready_target(exe.parent, '1.3.1') is None
    assert offsets == [0, cut]


def test_slow_progress_keeps_download_alive_beyond_fifteen_minutes(tmp_path, monkeypatch):
    from itertools import count
    tick = count(0, 11)
    monkeypatch.setattr(updater, 'monotonic', lambda: next(tick))
    data = bytes(range(200))
    class Slow(Response):
        def read1(self, n):
            return super().read1(1)
    progress = []
    dest = tmp_path / 'package.zip'
    updater._download(package('1.4.0', data), dest, lambda _, offset: Slow(data), progress.append)
    assert dest.read_bytes() == data and next(tick) > 900
    assert len(progress) == len(data) and progress[-1] == 100


def test_a_bounded_number_of_reconnections_leaves_application_usable(exe, monkeypatch):
    attempts, delays = [], []
    monkeypatch.setattr(updater, 'sleep', delays.append)
    def unavailable(_, offset):
        attempts.append(offset)
        raise TimeoutError('offline')
    with pytest.raises(ConnectionError):
        updater.prepare_package(exe, '1.3.1', package('1.4.0', b'example'), open_asset=unavailable)
    assert attempts == [0, 0, 0, 0] and delays == [1, 2, 4]
    assert exe.read_bytes() == b'working bootstrap' and updater.ready_target(exe.parent, '1.3.1') is None


def test_range_request_survives_the_github_asset_redirect(monkeypatch):
    seen = []
    class Opener:
        def open(self, request, timeout):
            seen.append((request, timeout))
    monkeypatch.setattr(updater, 'build_opener', lambda *_: Opener())
    pkg = package('1.4.0', b'example')
    updater.open_package(pkg, 3)
    req, timeout = seen[0]
    assert timeout == updater.SOCKET_TIMEOUT and req.full_url == pkg.url
    redirected = updater._AssetRedirect().redirect_request(req, None, 302, '', {},
                                                          'https://release-assets.githubusercontent.com/example')
    assert redirected.get_header('Range') == 'bytes=3-'
