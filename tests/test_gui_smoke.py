"""GUI smoke test runs with the offscreen Qt platform on CI."""
from tests.helpers import seed_event
import os

import pytest


def test_main_window_can_be_created(tmp_path, monkeypatch):
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from director_control.storage import Store
    from director_control.ui import MainWindow

    _app = QApplication.instance() or QApplication([])
    window = MainWindow(Store(tmp_path / "gui.db"))
    assert window.tabs.count() == 4
    assert window.table.rowCount() == 0
    from PySide6.QtWidgets import QPushButton
    assert not any("демо" in button.text().lower() for button in window.findChildren(QPushButton))
    assert not hasattr(window, "demo")
    assert not hasattr(window.store, "seed_demo")
    window.close()


def test_mail_panel_syncs_in_background_and_updates_window(tmp_path, monkeypatch):
    from datetime import date
    from time import monotonic
    from PySide6.QtCore import QThread
    from PySide6.QtWidgets import QApplication
    from director_control.credentials import Credentials
    from director_control.mail_calendar import CalendarConfig, parse_calendars
    from director_control.storage import Store
    from director_control.ui import MainWindow

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(Credentials, "can_remember", property(lambda self: False))
    seen = []
    config = CalendarConfig("https://calendar.mail.ru/principals/test/calendars/example/", "demo@example.test")
    def fetch(config, password, start, end):
        seen.append(QThread.currentThread() != app.thread())
        assert password == "test-only-password"
        return parse_calendars(["BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:gui\r\n"
            "DTSTART:20261022T090000Z\r\nDTEND:20261022T100000Z\r\nSUMMARY:GUI test\r\n"
            "END:VEVENT\r\nEND:VCALENDAR\r\n"], config, date(2026, 10, 1), date(2026, 11, 1))
    monkeypatch.setattr("director_control.mail_ui.fetch_snapshot", fetch)
    store = Store(tmp_path / "gui-sync.db")
    window = MainWindow(store)
    panel = window.mail_panel
    panel.auto.setChecked(False)
    panel.url.setText(config.url)
    panel.login.setText(config.username)
    panel.password.setText("test-only-password")
    panel.save_connection()
    deadline = monotonic() + 5
    while panel.worker is not None and monotonic() < deadline:
        app.processEvents()
        QThread.msleep(5)
    assert panel.worker is None
    assert seen == [True]
    assert len(store.daily_events("2026-10-22")) == 1
    assert "новых 1" in panel.status.text()
    assert panel.password.text() == ""
    assert "test-only-password" not in store.path.read_bytes().decode("latin-1")
    window.close()


def test_partial_mail_result_is_not_presented_as_complete_success(tmp_path):
    from PySide6.QtWidgets import QApplication
    from director_control.mail_calendar import CalendarSnapshot
    from director_control.storage import Store
    from director_control.ui import MainWindow

    _app = QApplication.instance() or QApplication([])
    store = Store(tmp_path / "partial.db")
    store.set_setting("mail_last_sync", "2026-10-21T10:00:00")
    window = MainWindow(store)
    snapshot = CalendarSnapshot("test", "2026-10-01T00:00:00", "2026-11-01T00:00:00", (),
                                ("ресурс 3 из 20: calendar-data 404; GET 404",))
    window.mail_panel.apply_snapshot(snapshot)
    assert "частично" in window.mail_panel.status.text()
    assert "недоступных записей 1" in window.mail_panel.status.text()
    assert "обновлён" not in window.mail_panel.status.text()
    assert store.get_setting("mail_last_sync") == "2026-10-21T10:00:00"
    window.close()


def test_calendar_modes_search_mail_only_and_period_navigation(tmp_path):
    from PySide6.QtCore import QDate
    from PySide6.QtWidgets import QApplication
    from director_control.storage import Store
    from director_control.ui import MainWindow

    _app = QApplication.instance() or QApplication([])
    store = Store(tmp_path / "modern.db")
    first = seed_event(store, "Встреча команды", "Работа", "2026-10-22T09:00:00", "2026-10-22T10:00:00")
    second = seed_event(store, "Mail event", "Работа", "2026-10-22T12:00:00", "2026-10-22T13:00:00",
                                source="caldav", external_key="mail-modern-test")
    legacy = seed_event(store, "Старая ручная запись", "Работа", "2026-10-22T14:00:00", "2026-10-22T15:00:00", source="manual")
    window = MainWindow(store)
    window.date_input.setDate(QDate(2026, 10, 22))
    for mode, count in (("day", 1), ("week", 7), ("month", 42)):
        window.set_view(mode)
        assert len(window.calendar.days) == count
    window.set_view("agenda")
    assert window.table.rowCount() == 2
    window.search.setText("КОМАНДЫ")
    assert window.row_ids == [first]
    window.search.clear()
    assert not hasattr(window, "show_manual") and not hasattr(window, "show_mail")
    assert legacy not in window.row_ids and set(window.row_ids) == {first, second}
    window.set_view("week")
    window.shift_period(1)
    assert window.selected_day() == "2026-10-29"
    window.set_view("month")
    window.shift_period(1)
    assert window.selected_day() == "2026-11-29"
    window.close()


def test_event_inspector_and_quick_completion_preserve_plan_and_do_not_invent_fact(tmp_path):
    from PySide6.QtCore import QDate
    from PySide6.QtWidgets import QApplication
    from director_control.storage import Store
    from director_control.ui import MainWindow

    app = QApplication.instance() or QApplication([])
    store = Store(tmp_path / "inspector.db")
    eid = seed_event(store, "Meeting", "Работа", "2026-10-22T09:00:00", "2026-10-22T10:00:00")
    store.freeze_day("2026-10-22")
    window = MainWindow(store)
    window.date_input.setDate(QDate(2026, 10, 22))
    window.select_event(eid)
    assert window.inspector.title.text() == "Meeting"
    window.mark_done()
    event = store.get_event(eid)
    assert event.status == "done" and event.actual_start is None
    assert event.baseline_start == "2026-10-22T09:00:00"
    window.show()
    window.resize(1050, 720)
    app.processEvents()
    assert not window.inspector.isVisible()
    assert window.calendar.hour_height == 52
    window.close()


def test_redesigned_dialog_preserves_mail_plan_and_accepts_local_comment(tmp_path):
    from PySide6.QtWidgets import QApplication
    from director_control.storage import Store
    from director_control.ui import EventDialog

    _app = QApplication.instance() or QApplication([])
    store = Store(tmp_path / "dialog.db")
    eid = seed_event(store, "Mail title", "Работа", "2026-10-22T09:00:15", "2026-10-22T10:00:15",
                             source="caldav", external_key="dialog-test")
    dialog = EventDialog(store, store.get_event(eid))
    assert not dialog.title_input.isEnabled() and not dialog.start_input.isEnabled()
    dialog.note_input.setText("Local comment")
    dialog.save()
    assert store.get_event(eid).current_start == "2026-10-22T09:00:15"
    assert store.get_event(eid).note == "Local comment"
    with pytest.raises(TypeError):
        EventDialog(store)
    dialog.close()
