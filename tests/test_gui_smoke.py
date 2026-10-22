"""GUI smoke test runs with the offscreen Qt platform on CI."""
import os

import pytest


def test_main_window_can_be_created(tmp_path, monkeypatch):
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from director_control.storage import Store
    from director_control.ui import MainWindow

    app = QApplication.instance() or QApplication([])
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

    app = QApplication.instance() or QApplication([])
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
