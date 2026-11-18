"""Real old-exe -> new-installer acceptance on a disposable Windows CI runner."""
import ctypes
import argparse
from contextlib import closing
from io import BytesIO
from ctypes import wintypes
import json
import hashlib
import os
from pathlib import Path
import sqlite3
import re
import subprocess
import sys
import tempfile
import tomllib
import shutil
from time import monotonic, sleep
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def program_files(folder):
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in folder.rglob('*') if p.is_file()
            and not re.fullmatch(r'unins[0-9]+\.(exe|dat)', p.name, re.IGNORECASE)}


def retired_files():
    # This is the same explicit list compiled into the installer, not a directory glob.
    text = (ROOT / 'packaging/retired-files.iss').read_text(encoding='utf-8')
    return [p.replace('\\', '/') for p in re.findall(r'Name: "\{app\}\\([^"\r\n]+)"', text)]


def assert_installed_content(install, expected, sentinels):
    actual = program_files(install)
    wanted = expected | sentinels
    extra = sorted(actual.keys() - wanted.keys())
    missing = sorted(wanted.keys() - actual.keys())
    changed = sorted(path for path in actual.keys() & wanted.keys() if actual[path] != wanted[path])
    assert actual == wanted, f'Installed files differ: extra={extra}, missing={missing}, changed={changed}'


def windows(pid):
    user = ctypes.WinDLL('user32', use_last_error=True)
    user.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    user.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    user.IsWindowVisible.argtypes = (wintypes.HWND,)
    found = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    @callback_type
    def callback(hwnd, _):
        owner = wintypes.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user.IsWindowVisible(hwnd):
            title = ctypes.create_unicode_buffer(512)
            user.GetWindowTextW(hwnd, title, len(title))
            found.append((hwnd, title.value))
        return True
    user.EnumWindows.argtypes = (callback_type, wintypes.LPARAM)
    user.EnumWindows(callback, 0)
    return found


def open_app(exe, env, cwd):
    print(f'Launching: {ascii(str(exe))}', flush=True)
    process = subprocess.Popen([str(exe)], env=env, cwd=cwd)
    return wait_for_window(process, env)


def wait_for_window(process, env):
    deadline = monotonic() + 45
    while process.poll() is None and monotonic() < deadline:
        for hwnd, title in windows(process.pid):
            if title.startswith('Director Calendar —'):
                return process, hwnd
        sleep(.1)
    log = Path(env['LOCALAPPDATA']) / 'DirectorControl/startup-error.log'
    if log.is_file():
        print(ascii(log.read_text(encoding='utf-8')), flush=True)
    print('Visible windows: ' + ascii(windows(process.pid)), flush=True)
    process.kill()
    process.wait()
    raise AssertionError('Packaged GUI did not open')


def close_app(process, hwnd):
    # Let automatic backup finish before requesting close; repeat if it was busy.
    user = ctypes.WinDLL('user32')
    user.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    deadline = monotonic() + 20
    while process.poll() is None and monotonic() < deadline:
        user.PostMessageW(hwnd, 0x10, 0, 0)
        sleep(.5)
    if process.poll() is None:
        process.kill()
        process.wait()
        raise AssertionError('GUI did not shut down cleanly')
    assert process.returncode == 0


def snapshot(path):
    with closing(sqlite3.connect(path)) as con:
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN ('settings','sqlite_sequence')")]
        result = {name: con.execute('SELECT * FROM "' + name + '" ORDER BY rowid').fetchall() for name in tables}
        result['settings'] = con.execute("SELECT * FROM settings WHERE key NOT IN ('app_last_version','backup_last_auto') ORDER BY key").fetchall()
        return result


def setup(executable, folder, env, *, success=True):
    print(f'Installer: {executable.name}, expected success={success}', flush=True)
    result = subprocess.run([str(executable), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART',
                             '/SP-', '/DIR=' + str(folder), '/LOG=' + str(folder.parent / (executable.stem+'.log'))],
                            env=env, timeout=180)
    assert (result.returncode == 0) == success, result.returncode



def uninstall(folder, env):
    # Inno may allocate unins001 after a previous loader is still cleaning itself up.
    candidates = [p.with_suffix('.exe') for p in folder.glob('unins*.dat')]
    assert len(candidates) == 1, candidates
    print('Uninstalling: ' + candidates[0].name, flush=True)
    subprocess.run([str(candidates[0]), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART'],
                   env=env, check=True, timeout=120)
    deadline = monotonic() + 30
    while monotonic() < deadline:
        if not (folder / 'DirectorCalendar.exe').exists() and not list(folder.glob('unins*.dat')):
            return
        sleep(.1)
    raise AssertionError('Uninstall did not finish removing program files')


def verify_package_update(exe, env, previous_version, original_database, expected):
    """Run the exact portable release with an independent, previous-version profile."""
    from director_control import __version__
    from director_control.package_update import Package, prepare_package, launch_ready

    archive = ROOT / f'dist/artifacts/DirectorCalendar-{__version__}-portable-x64.zip'
    with archive.open('rb') as stream:
        package = Package(__version__, archive.stat().st_size, hashlib.file_digest(stream, 'sha256').hexdigest())

    offsets = []
    cutoff = 64 * 1024
    def local_response(requested, offset):
        assert requested == package
        offsets.append(offset)
        if offset == 0:
            with archive.open('rb') as stream:
                response = BytesIO(stream.read(cutoff))
            response.status = 200
        else:
            response = archive.open('rb')
            response.seek(offset)
            response.status = 206
            response.headers = {'Content-Range': f'bytes {offset}-{package.size - 1}/{package.size}'}
        return response

    profile = original_database.parent.parent / 'Package update profile'
    profile.mkdir()
    database = profile / 'director_control.db'
    shutil.copyfile(original_database, database)
    before = database.read_bytes()
    # Only the HTTP body is supplied locally. Verification, extraction, the
    # frozen startup probe and the normal handoff all use production code.
    target = prepare_package(exe, previous_version, package, open_asset=local_response)
    assert offsets == [0, cutoff]
    assert database.read_bytes() == before
    assert (target.parent / 'version.txt').read_text(encoding='ascii').strip() == __version__
    update_env = dict(env, DIRECTOR_CONTROL_DATA_DIR=str(profile))
    process = launch_ready(exe, previous_version, environ=update_env)
    assert process is not None
    process, hwnd = wait_for_window(process, update_env)
    close_app(process, hwnd)
    assert snapshot(database) == expected
    with closing(sqlite3.connect(database)) as con:
        assert con.execute("SELECT value FROM settings WHERE key='app_last_version'").fetchone()[0] == __version__
    backups = list((profile / 'backups').glob('before-update-*.db'))
    assert len(backups) == 1 and snapshot(backups[0]) == expected
    # Uninstall must clean the package while preserving unrelated user additions.
    personal = target.parent / '_internal' / 'personal-note.txt'
    personal.write_bytes(b'not package-owned')
    return personal


def main(previous_root, output, upgrade_source, previous_installer=None):
    from keyring.backends.Windows import WinVaultKeyring
    from director_control import __version__
    from director_control.storage import default_data_dir
    previous_version = tomllib.loads((previous_root / 'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
    previous_commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=previous_root, text=True).strip()
    from scripts.release import verify_previous_installer
    selected = json.loads(upgrade_source.read_text(encoding='utf-8-sig'))
    assert selected['version'] == previous_version and selected['sha'] == previous_commit
    if selected['bootstrap']:
        assert previous_installer is None
        old_setup = next((previous_root / 'dist/artifacts').glob('*Setup-x64.exe'))
        previous_digest = None
    else:
        assert previous_installer is not None
        old_setup = previous_installer
        previous_digest = verify_previous_installer(old_setup, selected)
    new_setup = ROOT / f'dist/artifacts/DirectorCalendar-{__version__}-Setup-x64.exe'
    vault = WinVaultKeyring()
    key = 'distribution-upgrade-' + str(uuid4())
    vault.set_password('DirectorControl.CalDAV', key, 'synthetic-credential')
    report = {}
    try:
        with tempfile.TemporaryDirectory(prefix='DirectorCalendar-distribution-') as directory:
            temp = Path(directory)
            install = temp / "Профиль O'Neil & тест" / 'Программа'
            install.parent.mkdir()
            env = dict(os.environ)
            for name in ('PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV', 'QT_QPA_PLATFORM', 'DIRECTOR_CONTROL_DATA_DIR'):
                env.pop(name, None)
            env['LOCALAPPDATA'] = str(temp / 'Профиль пользователя')
            env['PATH'] = os.environ['SystemRoot'] + '\\System32;' + os.environ['SystemRoot']
            database = Path(env['LOCALAPPDATA']) / 'DirectorControl/director_control.db'
            # Seed with the actual previous revision's storage, like an existing Python installation.
            seed = """
from director_control.storage import Store
from director_control import __version__
s=Store()
s.set_setting('app_last_version', __version__)
e=s.create_event('Synthetic plan', 'Работа', '2026-10-29T09:00:00','2026-10-29T10:00:00',actual_start='2026-10-29T09:05:00',actual_end='2026-10-29T10:05:00',status='done',note='preserve')
s.freeze_day('2026-10-29')
s.create_event('Synthetic unplanned','Работа',actual_start='2026-10-29T12:00:00',actual_end='2026-10-29T12:30:00')
s.set_setting('ui_theme','dark')
s.set_setting('mail_login','synthetic@example.test')
s.set_setting('mail_auto','0')
# Daily-backup workers have separate entry-point tests; isolate update acceptance.
s.set_setting('backup_auto','0')
s.set_setting('app_auto_updates','0')
s.set_setting('ui_calendar_view','month')
"""
            subprocess.run([sys.executable, '-c', seed], cwd=previous_root, env=env, check=True, timeout=30)
            expected = snapshot(database)
            setup(old_setup, install, env)
            expected_files = program_files(ROOT / 'dist/DirectorCalendar')
            old_files = program_files(install)
            exe = install / 'DirectorCalendar.exe'
            process, hwnd = open_app(exe, env, temp)
            close_app(process, hwnd)
            assert snapshot(database) == expected
            # Simulate leftovers inherited through v0.13.4 -> v0.13.5 -> current.
            for relative in retired_files():
                path = install / relative
                if relative not in expected_files and not path.exists():
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b'owned obsolete file from an earlier release')
            sentinels = {}
            for relative in ('personal-notes.txt', '_internal/user-kept-file.txt',
                             '_internal/PySide6/plugins/imageformats/keep-user-data.txt'):
                path = install / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'user content must survive update and uninstall')
                sentinels[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
            # Reject junctions before cleanup/copy, leaving their external target intact.
            outside = temp / 'external-user-data'
            outside.mkdir()
            sentinel = outside / 'keep.db'
            sentinel.write_bytes(b'not application-owned')
            junction = install / '_internal' / 'unexpected-junction'
            junction_env = dict(env, DIRECTOR_TEST_LINK=str(junction), DIRECTOR_TEST_TARGET=str(outside))
            subprocess.run([str(Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'), '-NoProfile', '-NonInteractive', '-Command',
                            'New-Item -ItemType Junction -Path $env:DIRECTOR_TEST_LINK -Target $env:DIRECTOR_TEST_TARGET | Out-Null'],
                           env=junction_env, check=True, timeout=15)
            before_rejection = database.read_bytes()
            try:
                setup(new_setup, install, env, success=False)
                assert sentinel.read_bytes() == b'not application-owned'
                assert database.read_bytes() == before_rejection
            finally:
                # rmdir removes this temporary junction itself, not its target contents.
                os.rmdir(junction)
            setup(new_setup, install, env)
            assert_installed_content(install, expected_files, sentinels)
            assert snapshot(database) == expected  # Installer itself never touches data.
            process, hwnd = open_app(exe, env, temp)
            try:
                # Running app must stop an unattended update, without terminating it.
                setup(new_setup, install, env, success=False)
                assert process.poll() is None
            finally:
                close_app(process, hwnd)
            assert snapshot(database) == expected
            backups = list(database.parent.glob('backups/before-update-*.db'))
            assert len(backups) == 1 and snapshot(backups[0]) == expected
            with closing(sqlite3.connect(database)) as con:
                assert con.execute("SELECT value FROM settings WHERE key='app_last_version'").fetchone()[0] == __version__
            assert vault.get_password('DirectorControl.CalDAV', key) == 'synthetic-credential'
            # Reinstall and relaunch are idempotent; no duplicate version backup.
            setup(new_setup, install, env)
            assert_installed_content(install, expected_files, sentinels)
            process, hwnd = open_app(exe, env, temp)
            close_app(process, hwnd)
            assert len(list(database.parent.glob('backups/before-update-*.db'))) == 1
            assert snapshot(database) == expected
            setup(old_setup, install, env, success=False)  # Explicit downgrade rejected.
            # Exercise bundled Qt, iCalendar, tzdata, CA store, Vault and backup/restore.
            checked = temp / 'bundle-check.json'
            result = subprocess.run([str(exe), '--verify-installation', str(checked)], cwd=temp, env=env, timeout=60)
            if checked.is_file():
                print(ascii(checked.read_text(encoding='utf-8')), flush=True)
            result.check_returncode()
            check = json.loads(checked.read_text(encoding='utf-8'))
            assert check['ok'] and check['frozen'] and check['version'] == __version__
            assert Path(check['shortcut_target']).samefile(exe)
            personal = verify_package_update(exe, env, previous_version, backups[0], expected)
            sentinels[personal.relative_to(install).as_posix()] = hashlib.sha256(personal.read_bytes()).hexdigest()
            cache_marker = install / '.director-updates' / '.owner'
            sentinels[cache_marker.relative_to(install).as_posix()] = hashlib.sha256(cache_marker.read_bytes()).hexdigest()
            # Uninstall must retain DB/backups/settings/Vault. Then a clean reinstall reuses them.
            uninstall(install, env)
            assert program_files(install) == sentinels
            assert database.is_file() and snapshot(database) == expected and backups[0].is_file()
            assert vault.get_password('DirectorControl.CalDAV', key) == 'synthetic-credential'
            setup(new_setup, install, env)
            assert_installed_content(install, expected_files, sentinels)
            process, hwnd = open_app(exe, env, temp)
            close_app(process, hwnd)
            assert snapshot(database) == expected
            uninstall(install, env)
            assert program_files(install) == sentinels
            report.update(check, portable_update_verified=True, source_to_exe=True, old_to_new=True, reinstall=True, uninstall_preserves_data=True,
                          running_app_protected=True, downgrade_rejected=True, no_python_on_path=True,
                          default_data_directory=str(default_data_dir()), unicode_install_path=True,
                          previous_version=previous_version, previous_commit=previous_commit,
                          previous_installer_sha256=previous_digest, obsolete_files_removed=True,
                          user_files_preserved=True, installed_file_manifest=True, reparse_path_rejected=True,
                          removed_previous_files=sorted(set(old_files) - set(expected_files)))
    finally:
        vault.delete_password('DirectorControl.CalDAV', key)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Distribution acceptance passed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('previous_root', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--upgrade-source', required=True, type=Path)
    parser.add_argument('--previous-installer', default='')
    args = parser.parse_args()
    main(args.previous_root.resolve(), args.output.resolve(), args.upgrade_source.resolve(),
         Path(args.previous_installer).resolve() if args.previous_installer else None)
