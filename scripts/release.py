"""Versioned, verified GitHub Releases; only the publish job receives write access."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import tomllib
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from director_control.runtime_versions import verify_runtime

MAX_UPGRADE_ASSET = 512 * 1024 * 1024
BOOTSTRAP = {'tag': 'v0.10.0', 'version': '0.10.0',
             'sha': 'a7e524281a3026d501eb7232d68008f09700e3c3', 'bootstrap': True}
REQUIRED_CHECKS = ('ok', 'frozen', 'icon', 'caldav_parse', 'vault', 'backup_restore',
                   'backup_compatibility', 'emergency_restore', 'runtime_logging', 'gui', 'source_to_exe',
                   'old_to_new', 'reinstall', 'uninstall_preserves_data', 'running_app_protected',
                   'downgrade_rejected', 'no_python_on_path', 'unicode_install_path',
                   'sqlite_patched', 'untrusted_backup_rejected', 'obsolete_files_removed',
                   'user_files_preserved', 'installed_file_manifest', 'reparse_path_rejected', 'runtime_patched',
                   'backup_settings_validated', 'backup_destination_local',
                   'backup_records_validated', 'xml_runtime_verified')


def version_key(version):
    if not isinstance(version, str) or not re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', version):
        raise ValueError('Use a numeric MAJOR.MINOR.PATCH package version.')
    return tuple(map(int, version.split('.')))


def release_version(root=ROOT):
    version = tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
    version_key(version)
    module = ast.parse((root / 'director_control/__init__.py').read_text(encoding='utf-8'))
    values = [ast.literal_eval(node.value) for node in module.body if isinstance(node, ast.Assign)
              and any(isinstance(target, ast.Name) and target.id == '__version__' for target in node.targets)]
    if values != [version]:
        raise ValueError('Package and application versions differ.')
    return version


def release_notes(version, root=ROOT):
    notes = (root / 'releases' / f'v{version}.md').read_text(encoding='utf-8').strip()
    if not notes.startswith(f'# v{version}\n') or len(notes.splitlines()) < 3:
        raise ValueError('Provide English release notes headed by the exact vMAJOR.MINOR.PATCH tag.')
    return notes


class GitHub:
    def __init__(self, repository, token):
        self.repository, self.token = repository, token

    def request(self, path, method='GET', data=None, *, optional=False, upload=False):
        host = 'https://uploads.github.com' if upload else 'https://api.github.com'
        headers = {'Authorization': f'Bearer {self.token}', 'Accept': 'application/vnd.github+json',
                   'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'DirectorCalendar-Release'}
        if data is not None:
            headers['Content-Type'] = 'application/octet-stream' if upload else 'application/json'
            if not upload:
                data = json.dumps(data).encode()
        request = Request(f'{host}/repos/{self.repository}/{path}', data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=180) as response:
                content = response.read()
                return json.loads(content) if content else None
        except HTTPError as error:
            if optional and error.code == 404:
                return None
            raise RuntimeError(f'GitHub {method} {path} failed with HTTP {error.code}.') from error

    def releases(self):
        page = 1
        while True:
            batch = self.request(f'releases?per_page=100&page={page}')
            yield from batch
            if len(batch) < 100:
                return
            page += 1

    def tag_sha(self, tag):
        ref = self.request('git/ref/tags/' + quote(tag, safe=''), optional=True)
        if ref is None:
            return None
        obj = ref['object']
        for _ in range(10):
            if obj['type'] == 'commit':
                return obj['sha']
            if obj['type'] != 'tag':
                break
            obj = self.request('git/tags/' + obj['sha'])['object']
        raise ValueError('The release tag must resolve to a commit.')

    def download_asset(self, asset, destination):
        """Authenticated API download; never forward the token to asset storage."""
        class AssetRedirect(HTTPRedirectHandler):
            def redirect_request(self, request, fp, code, msg, headers, newurl):
                parts = urlsplit(newurl)
                if parts.scheme != 'https' or parts.username or parts.password or parts.port not in (None, 443):
                    raise ValueError('Invalid release asset redirect.')
                redirected = super().redirect_request(request, fp, code, msg, headers, newurl)
                if redirected is not None and parts.hostname != 'api.github.com':
                    redirected.remove_header('Authorization')
                return redirected

        validate_asset(asset)
        request = Request(f"https://api.github.com/repos/{self.repository}/releases/assets/{asset['id']}",
                          headers={'Authorization': f'Bearer {self.token}', 'Accept': 'application/octet-stream',
                                   'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'DirectorCalendar-Release'})
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with build_opener(AssetRedirect()).open(request, timeout=60) as response:
                with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as file:
                    temporary = Path(file.name)
                    hasher, size = hashlib.sha256(), 0
                    while chunk := response.read(1024 * 1024):
                        size += len(chunk)
                        if size > asset['size']:
                            raise ValueError('Downloaded asset exceeds its published size.')
                        hasher.update(chunk)
                        file.write(chunk)
            if size != asset['size'] or 'sha256:' + hasher.hexdigest() != asset['digest']:
                raise ValueError('Downloaded asset failed SHA-256/size verification.')
            temporary.replace(destination)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def validate_asset(asset):
    if (type(asset.get('id')) is not int or asset['id'] <= 0 or asset.get('state') != 'uploaded'
            or type(asset.get('size')) is not int or not 0 < asset['size'] <= MAX_UPGRADE_ASSET
            or not re.fullmatch(r'sha256:[0-9a-f]{64}', asset.get('digest') or '')):
        raise ValueError('A release asset must have a bounded size and published SHA-256.')


def download_previous_installer(api, previous, folder):
    """Use exactly the installer users received, bound to its tag and manifest."""
    folder = Path(folder)
    version_key(previous['version'])
    if (previous['tag'] != 'v' + previous['version']
            or not re.fullmatch(r'[0-9a-f]{40}', previous['sha'])):
        raise ValueError('Invalid previous source identity.')
    if previous['bootstrap']:
        return None
    published = api.request('releases/tags/' + previous['tag'])
    if (published['draft'] or published['tag_name'] != previous['tag']
            or previous['tag'] != 'v' + previous['version'] or api.tag_sha(previous['tag']) != previous['sha']):
        raise ValueError('Previous release/tag changed before download.')
    installer_name = f"DirectorCalendar-{previous['version']}-Setup-x64.exe"
    def asset_named(name):
        matches = [a for a in published['assets'] if a['name'] == name]
        if len(matches) != 1:
            raise ValueError('Missing or duplicate published upgrade asset.')
        validate_asset(matches[0])
        return matches[0]
    installer, manifest_asset = asset_named(installer_name), asset_named('release-manifest.json')
    if manifest_asset['size'] > 2 * 1024 * 1024:
        raise ValueError('Previous release manifest is too large.')
    manifest_path = folder / 'release-manifest.json'
    api.download_asset(manifest_asset, manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    recorded = manifest['files'].get(installer_name)
    if (manifest.get('version') != previous['version'] or manifest.get('tag') != previous['tag']
            or manifest.get('commit') != previous['sha']
            or manifest.get('tests') != 'success' or manifest.get('distribution') != 'success'
            or recorded != {'sha256': installer['digest'].removeprefix('sha256:'), 'size': installer['size']}):
        raise ValueError('Previous installer does not match its verified release manifest.')
    path = folder / installer_name
    api.download_asset(installer, path)
    if api.tag_sha(previous['tag']) != previous['sha']:
        raise ValueError('Previous source tag moved during download.')
    previous['installer'] = {'name': installer_name, 'sha256': recorded['sha256'], 'size': recorded['size'],
                             'asset_id': installer['id'], 'release_id': published['id']}
    return path


def verify_previous_installer(path, previous):
    """Recheck immediately before executing the old installer in acceptance."""
    info = previous['installer']
    path = Path(path)
    if (info['name'] != f"DirectorCalendar-{previous['version']}-Setup-x64.exe"
            or path.name != info['name'] or path.is_symlink() or not path.is_file()
            or path.stat().st_size != info['size'] or digest(path) != info['sha256']):
        raise ValueError('Previous installer changed before upgrade acceptance.')
    return info['sha256']


def previous_release(api, version):
    current = version_key(version)
    candidates = []
    for release in api.releases():
        tag = release['tag_name']
        if release['draft'] or not re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+', tag):
            continue
        key = version_key(tag[1:])
        if key < current:
            candidates.append((key, tag))
    if not candidates:
        if version_key(BOOTSTRAP['version']) >= current:
            raise ValueError('No older version is available for upgrade acceptance.')
        return dict(BOOTSTRAP)
    _, tag = max(candidates)
    sha = api.tag_sha(tag)
    if not sha:
        raise ValueError('The previous published release has no source tag.')
    return {'tag': tag, 'version': tag[1:], 'sha': sha, 'bootstrap': False}


def candidate(api, version, sha):
    if not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('A full source commit SHA is required.')
    tag = f'v{version}'
    existing = api.request('releases/tags/' + tag, optional=True)
    tagged = api.tag_sha(tag)
    if tagged is not None and tagged != sha:
        raise ValueError('This version tag already points to another commit; bump the version.')
    if existing and existing['target_commitish'] != sha and existing['draft']:
        raise ValueError('An existing draft belongs to another source commit.')
    if existing and not existing['draft']:
        if tagged != sha:
            raise ValueError('The published release does not match this source commit.')
        return False
    return True


def digest(path):
    with path.open('rb') as file:
        return hashlib.file_digest(file, 'sha256').hexdigest()


def verify_bundle(folder, version, sha):
    binaries = {f'DirectorCalendar-{version}-Setup-x64.exe', f'DirectorCalendar-{version}-portable-x64.zip'}
    expected = binaries | {'build-info.txt', 'build-dependencies.txt', 'distribution-check.json',
                           'upgrade-source.json', 'SHA256SUMS.txt'}
    if {p.name for p in folder.iterdir()} != expected or any(not (folder / p).is_file() or
            (folder / p).is_symlink() or (folder / p).stat().st_size == 0 for p in expected):
        raise ValueError('The distribution file set is incomplete or unexpected.')
    checksums = {}
    for line in (folder / 'SHA256SUMS.txt').read_text(encoding='utf-8-sig').splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  ([A-Za-z0-9_.-]+)', line)
        if not match or match[2] in checksums:
            raise ValueError('Malformed or duplicate checksum entry.')
        checksums[match[2]] = match[1]
    if set(checksums) != binaries or any(digest(folder / name) != value for name, value in checksums.items()):
        raise ValueError('The installer or portable ZIP failed checksum verification.')
    info = (folder / 'build-info.txt').read_text(encoding='utf-8-sig')
    if not re.search(r'Source: ' + re.escape(sha) + r'\s*$', info):
        raise ValueError('The distribution was built from a different source commit.')
    report = json.loads((folder / 'distribution-check.json').read_text(encoding='utf-8-sig'))
    if report.get('version') != version or any(report.get(key) is not True for key in REQUIRED_CHECKS):
        raise ValueError('Distribution acceptance is incomplete or belongs to another version.')
    verify_runtime(report)
    if (report.get('sqlite_version') != '3.54.1' or
            report.get('sqlite_source_id') != '2026-10-16 14:45:20 555e07ef33f69a0957d24d8e555b702464a131d6f1607f4c3c1e4551e8e6ca76'):
        raise ValueError('The distribution did not load the pinned SQLite library.')
    previous = json.loads((folder / 'upgrade-source.json').read_text(encoding='utf-8-sig'))
    if (previous.get('tag') != 'v' + previous['version'] or
            version_key(previous['version']) >= version_key(version) or
            not re.fullmatch(r'[0-9a-f]{40}', previous['sha']) or
            report.get('previous_version') != previous['version'] or report.get('previous_commit') != previous['sha']):
        raise ValueError('Upgrade acceptance does not match its selected previous version.')
    if not previous.get('bootstrap'):
        installer = previous.get('installer', {})
        if (installer.get('name') != f"DirectorCalendar-{previous['version']}-Setup-x64.exe"
                or not re.fullmatch(r'[0-9a-f]{64}', installer.get('sha256') or '')
                or not isinstance(installer.get('size'), int) or installer['size'] <= 0
                or report.get('previous_installer_sha256') != installer['sha256']):
            raise ValueError('Upgrade acceptance is not bound to the published previous installer.')
    return previous


def publish(api, folder, version, sha, notes, results, run_id):
    if results != ('success', 'success'):
        raise ValueError('Both tests and distribution jobs must succeed before publication.')
    previous = verify_bundle(folder, version, sha)
    if not candidate(api, version, sha):
        return
    # A queued release must not publish an outdated main revision.
    if api.request('git/ref/heads/main')['object']['sha'] != sha:
        raise ValueError('main moved; run Release again from the current main commit.')
    manifest = {'tag': f'v{version}', 'version': version, 'commit': sha, 'workflow_run_id': run_id,
                'tests': results[0], 'distribution': results[1], 'upgrade_from': previous,
                'files': {p.name: {'sha256': digest(p), 'size': p.stat().st_size}
                          for p in folder.iterdir() if p.name != 'SHA256SUMS.txt'}}
    (folder / 'release-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    files = sorted(p for p in folder.iterdir() if p.name != 'SHA256SUMS.txt')
    (folder / 'SHA256SUMS.txt').write_text(''.join(f'{digest(p)}  {p.name}\n' for p in files), encoding='ascii')
    files.append(folder / 'SHA256SUMS.txt')
    tag = f'v{version}'
    if api.tag_sha(tag) is None:
        api.request('git/refs', 'POST', {'ref': 'refs/tags/' + tag, 'sha': sha})
    release = api.request('releases/tags/' + tag, optional=True)
    body = notes + f'\n\nSource commit: `{sha}`. [Verification run](https://github.com/{api.repository}/actions/runs/{run_id}).\n'
    metadata = {'tag_name': tag, 'target_commitish': sha, 'name': tag, 'body': body,
                'draft': True, 'prerelease': version_key(version)[0] == 0}
    if release is None:
        release = api.request('releases', 'POST', metadata)
    else:
        if not release['draft'] or release['target_commitish'] != sha:
            raise ValueError('The release changed; published assets will not be overwritten.')
        release = api.request(f"releases/{release['id']}", 'PATCH', metadata)
    release_id = release['id']
    # Only unpublished draft assets may be replaced during a retry.
    for asset in api.request(f'releases/{release_id}/assets?per_page=100'):
        api.request(f"releases/assets/{asset['id']}", 'DELETE')
    for file in files:
        asset = api.request(f'releases/{release_id}/assets?name=' + quote(file.name), 'POST',
                            file.read_bytes(), upload=True)
        if asset.get('digest') != 'sha256:' + digest(file) or asset.get('size') != file.stat().st_size:
            raise ValueError('An uploaded asset failed verification; the release remains a draft.')
    uploaded = api.request(f'releases/{release_id}/assets?per_page=100')
    expected = {p.name: (p.stat().st_size, 'sha256:' + digest(p)) for p in files}
    if {a['name']: (a['size'], a.get('digest')) for a in uploaded} != expected:
        raise ValueError('The uploaded release is incomplete; it remains a draft.')
    if api.tag_sha(tag) != sha or api.request('git/ref/heads/main')['object']['sha'] != sha:
        raise ValueError('The source reference moved; the release remains a draft.')
    api.request(f'releases/{release_id}', 'PATCH', {'draft': False, 'make_latest': 'false' if metadata['prerelease'] else 'true'})
    print(f'Published {tag}: https://github.com/{api.repository}/releases/tag/{tag}')


def output(**values):
    for name, value in values.items():
        print(f'{name}={value}')
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as file:
            for name, value in values.items():
                file.write(f'{name}={value}\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'previous', 'publish'])
    parser.add_argument('--assets', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--installer-dir', type=Path)
    args = parser.parse_args()
    version = release_version()
    api = GitHub(os.environ['GITHUB_REPOSITORY'], os.environ['GH_TOKEN'])
    if args.command == 'previous':
        previous = previous_release(api, version)
        installer = download_previous_installer(api, previous, args.installer_dir) if args.installer_dir else None
        args.output.write_text(json.dumps(previous, indent=2) + '\n', encoding='utf-8')
        output(sha=previous['sha'], tag=previous['tag'], bootstrap=str(previous['bootstrap']).lower(),
               installer=str(installer.resolve()) if installer else '')
        return
    notes = release_notes(version)
    sha = os.environ['GITHUB_SHA']
    if args.command == 'prepare':
        output(publish=str(candidate(api, version, sha)).lower(), tag=f'v{version}')
    else:
        if os.environ.get('GITHUB_REF') != 'refs/heads/main':
            raise ValueError('Release publication is restricted to main.')
        publish(api, args.assets, version, sha, notes,
                (os.environ.get('RELEASE_TESTS_RESULT'), os.environ.get('RELEASE_DISTRIBUTION_RESULT')),
                os.environ['GITHUB_RUN_ID'])


if __name__ == '__main__':
    main()
