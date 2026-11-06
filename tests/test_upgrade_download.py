"""Use authentic published installers without weakening the upgrade gate."""
import copy
import hashlib
import io
import json
from urllib.request import Request

import pytest

from scripts import release
from tests.test_release import FakeGitHub, OLD_SHA, VERSION, bundle


def asset(name, body, identity):
    return dict(id=identity, name=name, state='uploaded', size=len(body),
                digest='sha256:'+hashlib.sha256(body).hexdigest())


class Published(FakeGitHub):
    def __init__(self):
        super().__init__()
        self.tags['v0.12.0'] = OLD_SHA
        self.installer = asset('DirectorCalendar-0.12.0-Setup-x64.exe', b'published installer', 1)
        self.manifest = dict(tag='v0.12.0', version='0.12.0', commit=OLD_SHA,
                             tests='success', distribution='success', files={self.installer['name']: {
                                 'size': self.installer['size'], 'sha256': self.installer['digest'][7:]}})
        self.downloads = []

    def request(self, path, **kwargs):
        assert path == 'releases/tags/v0.12.0'
        return dict(id=42, tag_name='v0.12.0', draft=False, assets=[self.installer,
                    asset('release-manifest.json', json.dumps(self.manifest).encode(), 2)])

    def download_asset(self, item, path):
        self.downloads.append(item['name'])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(json.dumps(self.manifest).encode() if item['id'] == 2 else b'published installer')


def previous():
    return dict(tag='v0.12.0', version='0.12.0', sha=OLD_SHA, bootstrap=False)


def test_download_is_bound_to_published_manifest_and_rechecked_before_execution(tmp_path):
    api, selected = Published(), previous()
    path = release.download_previous_installer(api, selected, tmp_path)
    assert path.read_bytes() == b'published installer'
    assert release.verify_previous_installer(path, selected) == api.installer['digest'][7:]
    assert selected['installer']['asset_id'] == 1 and selected['installer']['release_id'] == 42
    path.write_bytes(b'tampered')
    with pytest.raises(ValueError, match='changed before'):
        release.verify_previous_installer(path, selected)


@pytest.mark.parametrize('damage', ['commit', 'version', 'tests', 'distribution', 'checksum', 'size'])
def test_invalid_manifest_prevents_installer_download(tmp_path, damage):
    api = Published()
    if damage in {'checksum', 'size'}:
        api.manifest['files'][api.installer['name']]['sha256' if damage == 'checksum' else 'size'] = 'wrong'
    else:
        api.manifest[damage] = 'wrong'
    with pytest.raises(ValueError, match='manifest'):
        release.download_previous_installer(api, previous(), tmp_path)
    assert api.downloads == ['release-manifest.json']


@pytest.mark.parametrize('damage', ['draft', 'missing', 'duplicate', 'digest', 'tag'])
def test_bad_previous_release_fails_closed_without_rebuilding(tmp_path, damage):
    api = Published()
    good_request = api.request
    def changed(*args, **kwargs):
        result = good_request(*args, **kwargs)
        if damage == 'draft':
            result['draft'] = True
        elif damage == 'missing':
            result['assets'] = result['assets'][1:]
        elif damage == 'duplicate':
            result['assets'].append(copy.deepcopy(api.installer))
        elif damage == 'digest':
            result['assets'][0]['digest'] = None
        elif damage == 'tag':
            api.tags['v0.12.0'] = 'd'*40
        return result
    api.request = changed
    with pytest.raises(ValueError):
        release.download_previous_installer(api, previous(), tmp_path)
    assert not api.downloads


def test_moved_tag_after_download_stops_acceptance(tmp_path):
    api = Published()
    original = api.download_asset
    def moved(item, path):
        original(item, path)
        if item['id'] == 1:
            api.tags['v0.12.0'] = 'e'*40
    api.download_asset = moved
    with pytest.raises(ValueError, match='moved'):
        release.download_previous_installer(api, previous(), tmp_path)


def test_bootstrap_remains_available_only_for_no_release_case(tmp_path):
    api = Published()
    assert release.download_previous_installer(api, release.BOOTSTRAP, tmp_path) is None
    assert not api.downloads


@pytest.mark.parametrize('body', [b'valid installer', b'altered', b'valid installer EXTRA'])
def test_actual_download_verifies_bytes_and_never_forwards_token(monkeypatch, tmp_path, body):
    api = release.GitHub('example/calendar', 'SECRET')
    info = asset('old.exe', b'valid installer', 7)
    destination = tmp_path/'old.exe'
    destination.write_bytes(b'previous verified copy')
    class Opener:
        def open(self, request, **kwargs):
            assert request.full_url == 'https://api.github.com/repos/example/calendar/releases/assets/7'
            assert request.get_header('Authorization') == 'Bearer SECRET'
            return io.BytesIO(body)
    def opener(handler):
        request = Request('https://api.github.com/repos/example/calendar/releases/assets/7',
                          headers={'Authorization': 'Bearer SECRET', 'Accept': 'application/octet-stream'})
        redirected = handler.redirect_request(request, None, 302, '', {},
                                              'https://release-assets.githubusercontent.com/signed')
        assert not redirected.has_header('Authorization')
        with pytest.raises(ValueError):
            handler.redirect_request(request, None, 302, '', {}, 'http://example.test/unsafe')
        return Opener()
    monkeypatch.setattr(release, 'build_opener', opener)
    if body == b'valid installer':
        api.download_asset(info, destination)
        assert destination.read_bytes() == body
    else:
        with pytest.raises(ValueError):
            api.download_asset(info, destination)
        assert destination.read_bytes() == b'previous verified copy'
    assert list(tmp_path.iterdir()) == [destination]


def test_release_gate_rejects_different_previous_installer_digest(tmp_path):
    folder = bundle(tmp_path)
    path = folder/'distribution-check.json'
    report = json.loads(path.read_text())
    report['previous_installer_sha256'] = '0'*64
    path.write_text(json.dumps(report))
    with pytest.raises(ValueError, match='published previous installer'):
        release.verify_bundle(folder, VERSION, 'a'*40)
