from dataclasses import replace
from datetime import datetime, timedelta

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QApplication, QMessageBox

from director_control.mail_calendar import CalendarSnapshot
from director_control.storage import Store
from director_control.ui import MainWindow

DAY = '2026-10-26'


def test_sync_readiness_is_scoped_to_calendar_day_and_latest_attempt(tmp_path, monkeypatch):
    store = Store(tmp_path / 'sync.db')
    snapshot = CalendarSnapshot('calendar', DAY+'T00:00:00', '2026-10-27T00:00:00', ())
    assert store.sync_warning(DAY, 'calendar')
    store.apply_calendar_snapshot(snapshot)
    assert not store.sync_warning(DAY, 'calendar')
    assert store.sync_warning('2026-10-27', 'calendar')
    assert store.sync_warning(DAY, 'other-calendar')
    store.apply_calendar_snapshot(replace(snapshot, start=DAY+'T12:00:00', calendar_key='half-day'))
    assert store.sync_warning(DAY, 'half-day')
    store.apply_calendar_snapshot(replace(snapshot, unavailable=('unavailable',)))
    assert 'частичным' in Store(store.path).sync_warning(DAY, 'calendar')
    store.record_sync_failure('calendar', snapshot.start, snapshot.end)
    assert 'ошибкой' in store.sync_warning(DAY, 'calendar')
    store.apply_calendar_snapshot(snapshot)
    assert not store.sync_warning(DAY, 'calendar')
    with store._connect() as con:
        con.execute('UPDATE calendar_syncs SET finished_at=?', ((datetime.now()-timedelta(minutes=31)).isoformat(),))
    assert '30 минут' in store.sync_warning(DAY, 'calendar')


def test_freeze_cannot_run_during_sync_and_warning_requires_confirmation(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    store = Store(tmp_path / 'freeze.db')
    window = MainWindow(store)
    window.set_date(QDate(2026, 10, 26))
    messages = []
    monkeypatch.setattr(QMessageBox, 'information', lambda *args: messages.append(args[2]))
    window.mail_panel.worker = object()
    window.freeze()
    assert messages and not store.is_frozen(DAY)
    window.mail_panel.worker = None
    window.mail_panel.busy_changed.emit(True)
    assert not window.freeze_button.isEnabled()
    window.mail_panel.busy_changed.emit(False)
    assert window.freeze_button.isEnabled()
    store.set_setting('mail_url', 'https://calendar.mail.ru/principals/test/calendars/test/')
    store.set_setting('mail_login', 'test@example.test')
    questions = []
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: questions.append(args[2]) or QMessageBox.StandardButton.No)
    window.freeze()
    assert 'Нет подтверждённого' in questions[-1] and not store.is_frozen(DAY)
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Yes)
    window.freeze()
    assert store.is_frozen(DAY)
    window.close()
    app.processEvents()
