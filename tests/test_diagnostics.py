"""Exercise failures, real Python/Qt hooks, bounded files and privacy at the sink."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from director_control import diagnostics


@pytest.fixture
def logs(tmp_path):
    diagnostics.shutdown()
    assert diagnostics.configure(tmp_path / 'logs')
    yield diagnostics.log_path()
    diagnostics.shutdown()


def read(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]


def test_error_types_stack_and_codes_are_kept_but_messages_and_locals_are_not(logs):
    secret = 'password=super-secret https://private:credential@mail.test/calendar?token=hidden'
    try:
        try:
            raise OSError(13, secret, '/private/user/calendar.db')
        except OSError as cause:
            raise RuntimeError('Confidential meeting: ' + secret) from cause
    except RuntimeError as exc:
        assert diagnostics.record_error('mail.fetch', exc)
    text = logs.read_text()
    assert all(value not in text for value in ('super-secret', 'credential', 'mail.test', 'Confidential', '/private/user'))
    entry = read(logs)[0]
    assert entry['operation'] == 'mail.fetch' and entry['version'].startswith('v')
    assert [e['type'] for e in entry['exceptions']] == ['RuntimeError', 'PermissionError']
    assert entry['exceptions'][1]['errno'] == 13
    assert entry['exceptions'][0]['frames'][-1]['file'] == 'test_diagnostics.py'


def test_exception_repr_and_str_are_never_called_and_operation_is_allowlisted(logs):
    class Dangerous(Exception):
        def __str__(self):
            raise AssertionError('Do not inspect exception messages')
        __repr__ = __str__
    assert diagnostics.record_error('my-secret-password', Dangerous('secret'))
    assert 'my-secret-password' not in logs.read_text()
    assert read(logs)[0]['exceptions'][0]['type'] == 'Dangerous'


def test_hidden_provider_cause_keeps_type_without_private_message(logs):
    from director_control.mail_calendar import CalendarError
    try:
        try:
            raise ConnectionError('private-provider-url-and-password')
        except ConnectionError:
            raise CalendarError('Safe user-facing message') from None
    except CalendarError as exc:
        assert diagnostics.record_error('mail.fetch', exc)
    assert [e['type'] for e in read(logs)[0]['exceptions']] == ['CalendarError', 'ConnectionError']
    assert 'private-provider' not in logs.read_text()


def test_sqlite_error_code_is_recorded_without_sql_or_database_content(logs, tmp_path):
    con = sqlite3.connect(tmp_path / 'private.db')
    try:
        try:
            con.execute('SELECT confidential_column FROM confidential_table')
        except sqlite3.Error as exc:
            assert diagnostics.record_error('history.load', exc)
    finally:
        con.close()
    assert read(logs)[0]['exceptions'][0]['sqlite_errorcode'] == 1
    assert 'confidential' not in logs.read_text()


def test_rotation_is_bounded_and_records_stay_complete(tmp_path, monkeypatch):
    monkeypatch.setattr(diagnostics, 'MAX_BYTES', 2048)
    with diagnostics.session(tmp_path):
        for _ in range(100):
            assert diagnostics.record_error('ui.action', ValueError('secret'))
    files = list(tmp_path.glob('director-calendar.log*'))
    assert len(files) == 4
    assert all(0 < p.stat().st_size <= 2048 for p in files)
    assert all(read(p) for p in files)


def test_parallel_worker_records_do_not_interleave(logs):
    with ThreadPoolExecutor(max_workers=8) as executor:
        assert all(executor.map(lambda _: diagnostics.record_error('backup.auto', OSError('secret')), range(100)))
    assert len(read(logs)) == 100


def test_unavailable_directory_and_failed_rotation_do_not_escape(tmp_path, monkeypatch, capsys):
    blocked = tmp_path / 'not-a-directory'
    blocked.write_text('occupied')
    assert not diagnostics.configure(blocked)
    assert not diagnostics.record_error('startup', RuntimeError('secret'))
    assert not diagnostics.available()
    assert diagnostics.configure(tmp_path / 'logs')
    handler = diagnostics._handler
    monkeypatch.setattr(handler, 'shouldRollover', lambda record: True)
    def fail():
        raise OSError('secret disk failure')
    monkeypatch.setattr(handler, 'doRollover', fail)
    assert not diagnostics.record_error('ui.action', RuntimeError('secret'))
    assert not diagnostics.available()
    assert capsys.readouterr().err == ''
    diagnostics.shutdown()


def test_installation_is_idempotent_and_shutdown_restores_hooks(logs):
    import threading
    old = sys.excepthook, threading.excepthook, sys.unraisablehook
    diagnostics.install_hooks()
    diagnostics.install_hooks()
    diagnostics.shutdown()
    assert (sys.excepthook, threading.excepthook, sys.unraisablehook) == old


def test_real_thread_unraisable_and_qt_slot_failures_are_logged(tmp_path):
    script = r'''
import gc, sys, threading
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from director_control import diagnostics
diagnostics.configure(Path(sys.argv[1]))
diagnostics.install_hooks()
def fail():
    raise RuntimeError('NEVER-WRITE-THIS-SECRET')
thread = threading.Thread(target=fail)
thread.start()
thread.join()
class Broken:
    def __del__(self):
        raise ValueError('NEVER-WRITE-THIS-SECRET')
obj = Broken()
del obj
gc.collect()
app = QApplication([])
QTimer.singleShot(0, fail)
QTimer.singleShot(100, app.quit)
app.exec()
diagnostics.shutdown()
'''
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path)],
                            env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    log = tmp_path / 'director-calendar.log'
    assert {e['operation'] for e in read(log)} == {'uncaught.thread', 'uncaught.unraisable', 'uncaught.gui'}
    assert 'NEVER-WRITE-THIS-SECRET' not in log.read_text() + result.stderr


def test_handled_sync_and_backup_failures_keep_ui_error_signals(logs, monkeypatch):
    from datetime import date
    from director_control import mail_ui, backup_ui
    from director_control.mail_calendar import CalendarConfig
    from director_control.storage import Store
    def fail(*args, **kwargs):
        raise RuntimeError('PRIVATE-CALENDAR-PASSWORD')
    monkeypatch.setattr(mail_ui, 'fetch_snapshot', fail)
    worker = mail_ui.SyncThread(CalendarConfig('https://calendar.mail.ru/private/', 'private@test.test'),
                               'PRIVATE-CALENDAR-PASSWORD', date(2026, 11, 3))
    messages = []
    worker.failed.connect(messages.append)
    worker.run()
    assert messages and worker.password == ''
    monkeypatch.setattr(backup_ui, 'create_backup', fail)
    backup = backup_ui.BackupWorker(Store(logs.parent / 'synthetic.db'), 'manual')
    backup.run()
    assert backup.error
    assert {e['operation'] for e in read(logs)} == {'mail.fetch', 'backup.manual'}
    assert 'PRIVATE-CALENDAR-PASSWORD' not in logs.read_text()


def test_settings_open_only_local_log_folder_and_copy_path(logs, monkeypatch):
    from PySide6.QtWidgets import QApplication
    from director_control import diagnostics_ui
    app = QApplication.instance() or QApplication([])
    panel = diagnostics_ui.DiagnosticsPanel()
    urls = []
    monkeypatch.setattr(diagnostics_ui.QDesktopServices, 'openUrl', lambda url: urls.append(url) or True)
    panel.open_button.click()
    assert urls[0].isLocalFile() and Path(urls[0].toLocalFile()) == logs.parent
    panel.copy_button.click()
    assert app.clipboard().text() == str(logs)
    monkeypatch.setattr(diagnostics_ui.QDesktopServices, 'openUrl', lambda url: False)
    panel.open_button.click()
    assert 'Не удалось' in panel.status.text()
    panel.close()


def test_uncaught_notice_is_queued_and_deduplicated(logs):
    from PySide6.QtWidgets import QApplication
    from director_control.diagnostics_ui import ErrorNotice
    app = QApplication.instance() or QApplication([])
    notice = ErrorNotice()
    diagnostics.set_notifier(notice.raised.emit)
    diagnostics._sys_hook(RuntimeError, RuntimeError('private'), None)
    diagnostics._sys_hook(RuntimeError, RuntimeError('private'), None)
    app.processEvents()
    assert notice.message is not None and notice.message.isVisible()
    assert 'private' not in notice.message.text()
    notice.message.close()
    app.processEvents()
    diagnostics.set_notifier(None)


def test_failed_notice_does_not_recurse_into_exception_hook(logs, monkeypatch):
    from PySide6.QtWidgets import QApplication
    from director_control import diagnostics_ui
    app = QApplication.instance() or QApplication([])
    notice = diagnostics_ui.ErrorNotice()
    def fail(*args):
        raise OSError('private')
    monkeypatch.setattr(diagnostics_ui, 'QMessageBox', fail)
    notice.raised.emit(True)
    app.processEvents()
    assert len(read(logs)) == 1 and notice.message is None


def test_log_directory_failure_does_not_prevent_application_start(tmp_path, monkeypatch):
    from director_control import launcher, ui
    diagnostics.shutdown()
    blocked = tmp_path / 'occupied'
    blocked.write_text('occupied')
    monkeypatch.setenv('DIRECTOR_CONTROL_DATA_DIR', str(blocked))
    monkeypatch.setattr(ui, 'run_app', lambda: 0)
    assert launcher.main() == 0
