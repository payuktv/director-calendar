import os
from datetime import datetime
from pathlib import Path
import subprocess
import sys

import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from director_control.instance import SingleInstance
from director_control.local_event_dialog import LocalEventDialog
from director_control.storage import EventConflictError, Store
from director_control.ui import EventDialog
from tests.test_mail_only import imported_snapshot


def test_stale_local_save_and_delete_are_atomic(tmp_path):
    app = QApplication.instance() or QApplication([])
    store = Store(tmp_path / 'conflict.db')
    eid = store.create_event('Срочно', 'Работа', actual_start='2026-10-26T11:00:00', actual_end='2026-10-26T11:30:00')
    original = store.get_event(eid)
    dialog = LocalEventDialog(store, datetime(2026, 10, 26, 11), original)
    other = Store(store.path)
    other.update_event(eid, status='partial', note='Изменено во втором окне')
    count = len(store.audit_log())
    dialog.note_input.setPlainText('Устаревший комментарий')
    dialog.save()
    assert 'изменилось' in dialog.error_label.text()
    assert store.get_event(eid).status == 'partial'
    assert store.get_event(eid).note == 'Изменено во втором окне'
    with pytest.raises(EventConflictError):
        store.delete_event(eid, expected_revision=original.revision)
    assert len(store.audit_log()) == count
    dialog.close()
    app.processEvents()


def test_source_sync_invalidates_an_open_imported_editor(tmp_path, monkeypatch):
    from dataclasses import replace
    from PySide6.QtWidgets import QMessageBox
    app = QApplication.instance() or QApplication([])
    store = Store(tmp_path / 'source-conflict.db')
    snapshot = imported_snapshot()
    store.apply_calendar_snapshot(snapshot)
    original = store.daily_events('2026-10-22')[0]
    dialog = EventDialog(store, original)
    store.apply_calendar_snapshot(replace(snapshot, events=(replace(snapshot.events[0], cancelled=True),)))
    messages = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: messages.append(args[2]))
    dialog.note_input.setText('Мой комментарий')
    dialog.save()
    assert messages and 'изменилось' in messages[0]
    assert store.get_event(original.id).status == 'cancelled'
    assert store.get_event(original.id).note == ''
    dialog.close()
    app.processEvents()


def test_single_instance_notifies_owner_and_releases_lock(tmp_path):
    app = QApplication.instance() or QApplication([])
    database = tmp_path / 'Календарь директора' / 'data.db'
    first, second = SingleInstance(database), SingleInstance(database)
    activated = []
    first.activated.connect(lambda: activated.append(True))
    try:
        assert first.acquire()
        assert not second.acquire()
        assert second.notify()
        QTest.qWait(650)
        app.processEvents()
        assert activated == [True]
        first.close()
        assert second.acquire()
    finally:
        first.close()
        second.close()


def test_single_instance_recovers_after_process_crash(tmp_path):
    app = QApplication.instance() or QApplication([])
    database = tmp_path / 'crash.db'
    script = '''
import os,sys
from PySide6.QtCore import QCoreApplication
from director_control.instance import SingleInstance
app=QCoreApplication([])
guard=SingleInstance(sys.argv[1])
assert guard.acquire()
print('owned',flush=True)
os._exit(0)
'''
    result = subprocess.run([sys.executable, '-c', script, str(database)], cwd=Path(__file__).resolve().parents[1],
                            env=dict(os.environ, QT_QPA_PLATFORM='offscreen'), capture_output=True, text=True, timeout=15)
    assert result.returncode == 0 and 'owned' in result.stdout, result.stderr
    guard = SingleInstance(database)
    try:
        assert guard.acquire()
    finally:
        guard.close()
    app.processEvents()
