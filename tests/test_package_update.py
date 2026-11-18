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
                                   open_asset=lambda p: Response(data), probe=probe)


@pytest.fixture
def exe(tmp_path):
    folder = tmp_path / "Календарь O'Neil & тест"
    folder.mkdir()
    path = folder / updater.APP
    path.write_bytes(b'working bootstrap')
    return path


@pytest.mark.parametrize('separator', ['/', '\\'])
def test_ready_on_next_launch_from_original_shortcut_after_complete_verification(exe, monkeypatch, separator):
    data = bundle('1.10.0', separator=separator)
    observations = []
    def probe(folder, version):
        assert (folder / updater.APP).read_bytes() == b'synthetic application'
        observations.append(updater.ready_target(exe.parent, '1.9.0'))
    target = stage(exe, '1.9.0', '1.10.0', data=data, probe=probe)
    assert observations == [None] and exe.read_bytes() == b'working bootstrap'
    assert updater.ready_target(exe.parent, '1.9.0') == target
    assert updater.ready_target(exe.parent, '1.10.0') is None
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
def test_bad_or_interrupted_package_cannot_displace_last_working_version(exe, failure):
    first = stage(exe, '1.3.0', '1.4.0')
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
    with pytest.raises(ValueError):
        stage(first, '1.4.0', '1.5.0', data=data, metadata=meta, probe=probe)
    assert updater.ready_target(exe.parent, '1.3.0') == first
    assert updater.ready_target(exe.parent, '1.4.0') is None
    assert not list((exe.parent / updater.CACHE).glob('stage-*'))


def test_retry_and_multiple_releases_prune_only_recorded_old_files(exe):
    first = stage(exe, '1.3.0', '1.4.0')
    note = first.parent / '_internal/personal.txt'
    note.write_text('mine')
    second = stage(first, '1.4.0', '1.5.0')
    assert stage(first, '1.4.0', '1.5.0', probe=lambda *_: pytest.fail('duplicate')) == second
    third = stage(second, '1.5.0', '1.6.0')
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
