"""Imported Mail.ru events remain read-only and historical manual records stay archived."""
import os
import sqlite3
from datetime import date

import pytest

from director_control.mail_calendar import CalendarConfig, parse_calendars
from director_control.storage import Store
from tests.helpers import LegacyStoreFixture, seed_event


def imported_snapshot():
    config = CalendarConfig("https://calendar.mail.ru/principals/test/calendars/only-mail/", "test@example.test")
    return parse_calendars(["BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:only-mail\r\n"
        "DTSTART:20261022T090000\r\nDTEND:20261022T100000\r\nSUMMARY:Встреча из Mail.ru\r\n"
        "END:VEVENT\r\nEND:VCALENDAR\r\n"], config, date(2026, 10, 22), date(2026, 10, 23))


@pytest.fixture(scope="module")
def app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_import_keeps_source_fields_read_only_when_local_creation_is_available(tmp_path):
    store = Store(tmp_path / "source.db")
    assert hasattr(store, "create_event") and hasattr(store, "delete_event")
    assert store.daily_events("2026-10-22") == []
    snapshot = imported_snapshot()
    assert store.apply_calendar_snapshot(snapshot)["added"] == 1
    assert store.apply_calendar_snapshot(snapshot)["added"] == 0
    event = store.daily_events("2026-10-22")[0]
    assert event.source == "caldav" and len(store.daily_events("2026-10-22")) == 1
    for field, value in (("title", "Изменено локально"), ("current_start", "2026-10-22T11:00:00"),
                         ("current_end", "2026-10-22T12:00:00")):
        with pytest.raises(ValueError, match="Mail.ru"):
            store.update_event(event.id, **{field: value})
    assert store.get_event(event.id) == event


def test_legacy_records_are_preserved_but_excluded_from_all_accounting(tmp_path):
    store = Store(tmp_path / "mixed.db")
    legacy = seed_event(store, "СТАРАЯ РУЧНАЯ ЗАПИСЬ", "Работа", "2026-10-22T07:00:00", "2026-10-22T19:00:00",
                        source="manual")
    LegacyStoreFixture.update_event(store, legacy, status="done", actual_start="2026-10-22T07:00:00",
                                    actual_end="2026-10-22T19:00:00", note="Сохранить историю")
    before = store.get_event(legacy)
    store.apply_calendar_snapshot(imported_snapshot())
    imported = store.daily_events("2026-10-22")[0]
    assert store.freeze_day("2026-10-22") == 1
    assert store.get_event(legacy) == before and store.get_event(legacy).baseline_start is None
    assert [event.id for event in store.daily_events("2026-10-22")] == [imported.id]
    assert [event.id for event in store.events_between("2026-10-22T00:00:00", "2026-10-23T00:00:00")] == [imported.id]
    summary = store.day_summary("2026-10-22")
    assert (summary["total"], summary["planned"], summary["done"], summary["pending"]) == (1, 1, 0, 1)
    assert store.category_totals("2026-10-22") == [("Mail.ru", 60, 0)]
    assert store.coverage_for_day("2026-10-22") == {"gaps": [("07:00", "09:00"), ("10:00", "19:00")], "overlaps": 0}
    report = tmp_path / "report.csv"
    store.export_csv("2026-10-22", report)
    assert "СТАРАЯ РУЧНАЯ" not in report.read_text(encoding="utf-8-sig")
    with pytest.raises(ValueError, match="Mail.ru"):
        store.update_event(legacy, status="cancelled")
    reopened = Store(store.path)
    assert reopened.get_event(legacy) == before
    assert any(row["event_id"] == legacy for row in reopened.audit_log())
    with sqlite3.connect(reopened.backup()) as con:
        assert con.execute("SELECT count(*) FROM events").fetchone()[0] == 2
        assert con.execute("SELECT note FROM events WHERE id=?", (legacy,)).fetchone()[0] == "Сохранить историю"


@pytest.mark.parametrize("mode", ["day", "week", "month"])
def test_empty_calendar_double_click_does_not_create_without_form_confirmation(app, tmp_path, monkeypatch, mode):
    from PySide6.QtCore import QDate, QPoint, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QPushButton
    from director_control import ui
    from director_control.calendar_view import GUTTER

    store = Store(tmp_path / "empty-ui.db")
    window = ui.MainWindow(store)
    window.date_input.setDate(QDate(2026, 10, 22))
    window.set_view(mode)
    window.show()
    app.processEvents()
    dialogs = []
    monkeypatch.setattr(ui, "EventDialog", lambda *args, **kwargs: dialogs.append(args))
    canvas = window.calendar.month if mode == "month" else window.calendar.grid
    point = QPoint(30, 65) if mode == "month" else QPoint(GUTTER + 30, 8 * window.calendar.hour_height + 10)
    QTest.mouseDClick(canvas, Qt.MouseButton.LeftButton, pos=point)
    app.processEvents()
    assert dialogs == [] and store.daily_events("2026-10-22") == []
    assert window.add_event_button.isEnabled()
    assert all(not hasattr(window, name) for name in ("add_at_time", "delete_event", "show_manual", "show_mail"))
    assert not hasattr(window.calendar, "slot_requested")
    assert not any(button.text() in {"Событие", "Удалить", "Удалить событие"} for button in window.findChildren(QPushButton))
    assert not hasattr(window.inspector, "delete_button")
    assert window.mail_refresh.text() == "Обновить Mail.ru"
    window.close()


def test_account_dialog_requires_existing_mail_event_and_saves_only_account_fields(app, tmp_path):
    from director_control.ui import EventDialog

    store = Store(tmp_path / "dialog.db")
    legacy = seed_event(store, "Ручная запись", "Работа", "2026-10-22T07:00:00", "2026-10-22T08:00:00", source="manual")
    with pytest.raises(TypeError):
        EventDialog(store)
    with pytest.raises(ValueError, match="Mail.ru"):
        EventDialog(store, store.get_event(legacy))
    store.apply_calendar_snapshot(imported_snapshot())
    event = store.daily_events("2026-10-22")[0]
    dialog = EventDialog(store, event)
    assert not dialog.title_input.isEnabled() and not dialog.start_input.isEnabled() and not dialog.end_input.isEnabled()
    dialog.title_input.setText("Попытка изменить источник")
    dialog.start_input.setDate(dialog.start_input.date().addDays(1))
    dialog.category_input.setCurrentText("Работа")
    dialog.status_input.setCurrentIndex(dialog.status_input.findData("partial"))
    dialog.note_input.setText("Локальный итог")
    dialog.save()
    saved = store.get_event(event.id)
    assert (saved.title, saved.current_start, saved.current_end) == (event.title, event.current_start, event.current_end)
    assert (saved.status, saved.category, saved.note, saved.actual_start) == ("partial", "Работа", "Локальный итог", None)
    dialog.close()
