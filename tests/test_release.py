"""A release must never expose incomplete, untested or mismatched binaries."""
import copy
import json

import pytest

from scripts import release
from director_control.runtime_versions import PYTHON_VERSION, EXPAT_VERSION, OPENSSL_VERSION

SHA = 'a' * 40
OLD_SHA = 'b' * 40
VERSION = '0.12.1'


class FakeGitHub:
    repository = 'example/calendar'

    def __init__(self):
        self.tags, self.listed, self.writes, self.assets = {}, [], [], []
        self.release = None
        self.main_sha = SHA
        self.upload_failure = False
        self.wrong_digest = False

    def releases(self):
        return iter(self.listed)

    def tag_sha(self, tag):
        return self.tags.get(tag)

    def request(self, path, method='GET', data=None, **options):
        if method != 'GET':
            self.writes.append((path, method, copy.deepcopy(data) if not isinstance(data, bytes) else '<binary>'))
        if path.startswith('releases/tags/'):
            return copy.deepcopy(self.release)
        if path == 'git/ref/heads/main':
            return {'object': {'sha': self.main_sha}}
        if path == 'git/refs':
            self.tags[data['ref'].removeprefix('refs/tags/')] = data['sha']
            return {}
        if path == 'releases' and method == 'POST':
            self.release = {'id': 1, **data}
            return copy.deepcopy(self.release)
        if path == 'releases/1' and method == 'PATCH':
            self.release.update(data)
            return copy.deepcopy(self.release)
        if method == 'DELETE':
            self.assets = [a for a in self.assets if str(a['id']) != path.rsplit('/', 1)[-1]]
            return None
        if path.startswith('releases/1/assets?name='):
            if self.upload_failure:
                raise OSError('Synthetic upload interruption')
            import hashlib
            asset = {'id': len(self.assets) + 1, 'name': path.split('name=')[1], 'size': len(data),
                     'digest': 'sha256:' + hashlib.sha256(data).hexdigest()}
            if self.wrong_digest:
                asset['digest'] = 'sha256:' + '0' * 64
            self.assets.append(asset)
            return asset
        if path == 'releases/1/assets?per_page=100':
            return copy.deepcopy(self.assets)
        raise AssertionError((path, method))


def bundle(tmp_path):
    folder = tmp_path / 'assets'
    folder.mkdir()
    for name in (f'DirectorCalendar-{VERSION}-Setup-x64.exe', f'DirectorCalendar-{VERSION}-portable-x64.zip'):
        (folder / name).write_bytes(b'synthetic binary ' + name.encode())
    (folder / 'build-info.txt').write_text('Python: test; Source: ' + SHA + '\n')
    (folder / 'build-dependencies.txt').write_text('synthetic==1.0\n')
    report = {key: True for key in release.REQUIRED_CHECKS}
    report.update(python_version=PYTHON_VERSION, expat_version=EXPAT_VERSION,
                  elementtree_version='Expat 2.10.0', elementtree_accelerated=True,
                  openssl_version=OPENSSL_VERSION, python_bits=64,
                  python_implementation='CPython', python_free_threaded=False)
    report.update(version=VERSION, previous_version='0.12.0', previous_commit=OLD_SHA,
                  previous_installer_sha256='c' * 64, sqlite_version='3.54.1',
                  sqlite_source_id='2026-10-16 14:45:20 555e07ef33f69a0957d24d8e555b702464a131d6f1607f4c3c1e4551e8e6ca76')
    (folder / 'distribution-check.json').write_text(json.dumps(report))
    previous = dict(tag='v0.12.0', version='0.12.0', sha=OLD_SHA, bootstrap=False,
                    installer={'name': 'DirectorCalendar-0.12.0-Setup-x64.exe', 'sha256': 'c'*64, 'size': 20})
    (folder / 'upgrade-source.json').write_text(json.dumps(previous))
    binaries = sorted(list(folder.glob('*.exe')) + list(folder.glob('*.zip')))
    (folder / 'SHA256SUMS.txt').write_text(''.join(f'{release.digest(p)}  {p.name}\n' for p in binaries))
    return folder


def publish(api, folder, results=('success', 'success')):
    release.publish(api, folder, VERSION, SHA, '# v0.12.1\n\nSynthetic notes.', results, '123')


def test_previous_release_uses_numeric_order_includes_prereleases_and_excludes_drafts():
    api = FakeGitHub()
    api.listed = [dict(tag_name=tag, draft=draft, prerelease=True) for tag, draft in
                  [('v0.9.0', False), ('v0.11.0', False), ('v0.12.0', False), ('v0.12.1', False),
                   ('v0.12.2', True), ('v0.13.0', False), ('nightly', False)]]
    api.tags['v0.12.0'] = OLD_SHA
    assert release.previous_release(api, VERSION) == dict(tag='v0.12.0', version='0.12.0', sha=OLD_SHA, bootstrap=False)


def test_first_release_uses_explicit_bootstrap_and_missing_tag_is_an_error():
    api = FakeGitHub()
    assert release.previous_release(api, VERSION) == release.BOOTSTRAP
    api.listed = [dict(tag_name='v0.12.0', draft=False)]
    with pytest.raises(ValueError, match='no source tag'):
        release.previous_release(api, VERSION)


def test_network_failure_does_not_silently_fall_back_to_bootstrap():
    class Broken(FakeGitHub):
        def releases(self):
            raise OSError('API unavailable')
    with pytest.raises(OSError):
        release.previous_release(Broken(), VERSION)


@pytest.mark.parametrize('results', [('failure', 'success'), ('success', 'failure'), ('skipped', 'success'),
                                     ('success', 'cancelled'), (None, 'success')])
def test_failed_or_missing_prerequisite_prevents_all_publication_writes(tmp_path, results):
    api = FakeGitHub()
    with pytest.raises(ValueError, match='Both tests'):
        publish(api, tmp_path / 'missing', results)
    assert not api.writes


@pytest.mark.parametrize('damage', ['missing', 'extra', 'binary', 'checksum', 'source', 'report', 'version', 'previous'])
def test_invalid_distribution_cannot_create_even_a_tag_or_draft(tmp_path, damage):
    folder = bundle(tmp_path)
    if damage == 'missing':
        (folder / 'build-dependencies.txt').unlink()
    elif damage == 'extra':
        (folder / 'unexpected.txt').write_text('extra')
    elif damage == 'binary':
        next(folder.glob('*.exe')).write_bytes(b'tampered')
    elif damage == 'checksum':
        (folder / 'SHA256SUMS.txt').write_text('invalid')
    elif damage == 'source':
        (folder / 'build-info.txt').write_text('Source: ' + OLD_SHA)
    elif damage in ('report', 'version'):
        file = folder / 'distribution-check.json'
        report = json.loads(file.read_text())
        report['backup_compatibility' if damage == 'report' else 'version'] = False if damage == 'report' else '9.0.0'
        file.write_text(json.dumps(report))
    else:
        file = folder / 'upgrade-source.json'
        previous = json.loads(file.read_text())
        previous['sha'] = SHA
        file.write_text(json.dumps(previous))
    api = FakeGitHub()
    with pytest.raises(ValueError):
        publish(api, folder)
    assert not api.writes


def test_published_release_is_complete_and_bound_to_the_checked_commit(tmp_path):
    folder, api = bundle(tmp_path), FakeGitHub()
    publish(api, folder)
    assert api.tags['v' + VERSION] == SHA
    assert api.release['draft'] is False and api.release['prerelease'] is True
    assert api.release['name'] == 'v' + VERSION and api.release['target_commitish'] == SHA
    assert len(api.assets) == 8
    assert api.writes[-1] == ('releases/1', 'PATCH', {'draft': False, 'make_latest': 'false'})
    checksums = (folder / 'SHA256SUMS.txt').read_text().splitlines()
    assert len(checksums) == 7
    for line in checksums:
        value, name = line.split('  ')
        assert release.digest(folder / name) == value
    manifest = json.loads((folder / 'release-manifest.json').read_text())
    assert manifest['commit'] == SHA and manifest['workflow_run_id'] == '123'
    assert manifest['upgrade_from']['sha'] == OLD_SHA


def test_first_stable_release_becomes_latest_only_after_verified_uploads(tmp_path, monkeypatch):
    monkeypatch.setitem(globals(), 'VERSION', '1.0.0')
    folder, api = bundle(tmp_path), FakeGitHub()
    notes = '# v1.0.0\n\nFirst stable release.'
    api.wrong_digest = True
    with pytest.raises(ValueError):
        release.publish(api, folder, VERSION, SHA, notes, ('success', 'success'), '123')
    assert api.release['draft'] is True and api.release['prerelease'] is False
    assert not any(data.get('draft') is False for _, _, data in api.writes if isinstance(data, dict))

    # The workflow rebuilds and validates a fresh bundle before retrying a draft.
    retry = tmp_path / 'retry'
    retry.mkdir()
    folder = bundle(retry)
    api.wrong_digest = False
    release.publish(api, folder, VERSION, SHA, notes, ('success', 'success'), '123')
    assert api.tags['v1.0.0'] == SHA
    assert api.release['draft'] is False and api.release['prerelease'] is False
    assert api.release['name'] == 'v1.0.0' and api.release['target_commitish'] == SHA
    assert len(api.assets) == 8
    assert api.writes[-1] == ('releases/1', 'PATCH', {'draft': False, 'make_latest': 'true'})


@pytest.mark.parametrize('failure', ['interrupted', 'digest'])
def test_upload_failure_leaves_unpublished_draft(tmp_path, failure):
    api = FakeGitHub()
    api.upload_failure = failure == 'interrupted'
    api.wrong_digest = failure == 'digest'
    with pytest.raises((OSError, ValueError)):
        publish(api, bundle(tmp_path))
    assert api.release['draft'] is True
    assert not any(data.get('draft') is False for _, _, data in api.writes if isinstance(data, dict))


def test_retry_replaces_only_same_commit_draft_assets(tmp_path):
    api = FakeGitHub()
    api.tags['v' + VERSION] = SHA
    api.release = dict(id=1, draft=True, target_commitish=SHA)
    api.assets = [dict(id=42, name='partial.exe', size=1, digest=None)]
    publish(api, bundle(tmp_path))
    assert ('releases/assets/42', 'DELETE', None) in api.writes
    assert api.release['draft'] is False


@pytest.mark.parametrize('change', ['missing-asset', 'moved-tag'])
def test_final_remote_state_is_checked_before_publication(tmp_path, change):
    class Changed(FakeGitHub):
        def request(self, path, method='GET', data=None, **options):
            result = super().request(path, method, data, **options)
            if path == 'releases/1/assets?per_page=100' and len(self.assets) == 8:
                if change == 'missing-asset':
                    return result[:-1]
                self.tags['v' + VERSION] = OLD_SHA
            return result
    api = Changed()
    with pytest.raises(ValueError, match='remains a draft'):
        publish(api, bundle(tmp_path))
    assert api.release['draft'] is True


@pytest.mark.parametrize('kind', ['tag', 'draft', 'main'])
def test_source_conflict_prevents_all_writes(tmp_path, kind):
    api = FakeGitHub()
    if kind == 'tag':
        api.tags['v' + VERSION] = OLD_SHA
    elif kind == 'draft':
        api.release = dict(id=1, draft=True, target_commitish=OLD_SHA)
    else:
        api.main_sha = OLD_SHA
    with pytest.raises(ValueError):
        publish(api, bundle(tmp_path))
    assert not api.writes


def test_existing_published_release_is_never_modified(tmp_path):
    api = FakeGitHub()
    api.tags['v' + VERSION] = SHA
    api.release = dict(id=1, draft=False, target_commitish=SHA)
    publish(api, bundle(tmp_path))
    assert not api.writes


def test_package_version_and_release_notes_must_agree(tmp_path):
    (tmp_path / 'director_control').mkdir()
    (tmp_path / 'releases').mkdir()
    (tmp_path / 'pyproject.toml').write_text('[project]\nversion="0.12.1"\n')
    init = tmp_path / 'director_control/__init__.py'
    init.write_text('__version__ = "0.12.0"\n')
    with pytest.raises(ValueError, match='differ'):
        release.release_version(tmp_path)
    init.write_text('__version__ = "0.12.1"\n')
    assert release.release_version(tmp_path) == VERSION
    notes = tmp_path / 'releases/v0.12.1.md'
    notes.write_text('# v0.12.0\n\nWrong version.\n')
    with pytest.raises(ValueError):
        release.release_notes(VERSION, tmp_path)
    notes.write_text('# v0.12.1\n\nEnglish notes.\n')
    assert release.release_notes(VERSION, tmp_path).startswith('# v0.12.1')


def test_annotated_tags_and_release_pagination(monkeypatch):
    api = release.GitHub('example/calendar', 'synthetic')
    pages = []
    def request(path, **kwargs):
        if path.startswith('releases?'):
            pages.append(path)
            return [dict(tag_name='v0.1.0')] * 100 if path.endswith('page=1') else []
        if path.startswith('git/ref/tags/'):
            return {'object': {'type': 'tag', 'sha': OLD_SHA}}
        if path == 'git/tags/' + OLD_SHA:
            return {'object': {'type': 'commit', 'sha': SHA}}
        raise AssertionError(path)
    monkeypatch.setattr(api, 'request', request)
    assert len(list(api.releases())) == 100 and len(pages) == 2
    assert api.tag_sha('v0.12.1') == SHA
