"""Real old-exe -> new-installer acceptance on a disposable Windows CI runner."""
import ctypes
from contextlib import closing
from ctypes import wintypes
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
from time import monotonic, sleep
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


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


def main(previous_root, output):
    from keyring.backends.Windows import WinVaultKeyring
    from director_control import __version__
    from director_control.storage import default_data_dir
    old_setup = next((previous_root / 'dist/artifacts').glob('*Setup-x64.exe'))
    new_setup = ROOT / f'dist/artifacts/DirectorCalendar-{__version__}-Setup-x64.exe'
    vault = WinVaultKeyring()
    key = 'distribution-upgrade-' + str(uuid4())
    vault.set_password('DirectorControl.CalDAV', key, 'synthetic-credential')
    report = {}
    try:
        with tempfile.TemporaryDirectory(prefix='DirectorCalendar-distribution-') as directory:
            temp = Path(directory)
            install = temp / "Компания O'Neil & команда" / 'Программа'
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
s=Store()
e=s.create_event('Synthetic plan', 'Работа', '2026-10-29T09:00:00','2026-10-29T10:00:00',actual_start='2026-10-29T09:05:00',actual_end='2026-10-29T10:05:00',status='done',note='preserve')
s.freeze_day('2026-10-29')
s.create_event('Synthetic unplanned','Работа',actual_start='2026-10-29T12:00:00',actual_end='2026-10-29T12:30:00')
s.set_setting('ui_theme','dark')
s.set_setting('mail_login','synthetic@example.test')
s.set_setting('mail_auto','0')
# Daily-backup workers have separate entry-point tests; isolate update acceptance.
s.set_setting('backup_auto','0')
s.set_setting('ui_calendar_view','month')
"""
            subprocess.run([sys.executable, '-c', seed], cwd=previous_root, env=env, check=True, timeout=30)
            expected = snapshot(database)
            setup(old_setup, install, env)
            exe = install / 'DirectorCalendar.exe'
            process, hwnd = open_app(exe, env, temp)
            close_app(process, hwnd)
            assert snapshot(database) == expected
            setup(new_setup, install, env)
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
            # Uninstall must retain DB/backups/settings/Vault. Then a clean reinstall reuses them.
            subprocess.run([str(install/'unins000.exe'), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART'], env=env, check=True, timeout=120)
            assert database.is_file() and snapshot(database) == expected and backups[0].is_file()
            assert vault.get_password('DirectorControl.CalDAV', key) == 'synthetic-credential'
            setup(new_setup, install, env)
            process, hwnd = open_app(exe, env, temp)
            close_app(process, hwnd)
            assert snapshot(database) == expected
            subprocess.run([str(install/'unins000.exe'), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART'], env=env, check=True, timeout=120)
            report.update(check, source_to_exe=True, old_to_new=True, reinstall=True, uninstall_preserves_data=True,
                          running_app_protected=True, downgrade_rejected=True, no_python_on_path=True,
                          default_data_directory=str(default_data_dir()), unicode_install_path=True)
    finally:
        vault.delete_password('DirectorControl.CalDAV', key)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Distribution acceptance passed')


if __name__ == '__main__':
    main(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
