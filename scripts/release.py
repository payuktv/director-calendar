"""Versioned, verified GitHub Releases; only the publish job receives write access."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import tomllib
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = {'tag': 'v0.10.0', 'version': '0.10.0',
             'sha': 'a7e524281a3026d501eb7232d68008f09700e3c3', 'bootstrap': True}
REQUIRED_CHECKS = ('ok', 'frozen', 'icon', 'caldav_parse', 'vault', 'backup_restore',
                   'backup_compatibility', 'emergency_restore', 'runtime_logging', 'gui', 'source_to_exe',
                   'old_to_new', 'reinstall', 'uninstall_preserves_data', 'running_app_protected',
                   'downgrade_rejected', 'no_python_on_path', 'unicode_install_path')


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
    previous = json.loads((folder / 'upgrade-source.json').read_text(encoding='utf-8-sig'))
    if (previous.get('tag') != 'v' + previous['version'] or
            version_key(previous['version']) >= version_key(version) or
            not re.fullmatch(r'[0-9a-f]{40}', previous['sha']) or
            report.get('previous_version') != previous['version'] or report.get('previous_commit') != previous['sha']):
        raise ValueError('Upgrade acceptance does not match its selected previous version.')
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
    args = parser.parse_args()
    version = release_version()
    api = GitHub(os.environ['GITHUB_REPOSITORY'], os.environ['GH_TOKEN'])
    if args.command == 'previous':
        previous = previous_release(api, version)
        args.output.write_text(json.dumps(previous, indent=2) + '\n', encoding='utf-8')
        output(sha=previous['sha'], tag=previous['tag'])
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
