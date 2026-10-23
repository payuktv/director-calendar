"""Calendar context menu interaction and preservation of schedule data."""
import json
import os
from dataclasses import replace
from datetime import date

import pytest


@pytest.fixture(scope="module")
def app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("mode,all_day", [
    ("day", False), ("week", False), ("month", False),
    ("day", True), ("week", True), ("month", True),
])
def test_context_request_targets_the_clicked_event_and_day(app, mode, all_day):
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QContextMenuEvent
    from director_control.calendar_view import CalendarBoard
    from director_control.storage import Event

    item = Event(1, "Двухдневное событие", "Работа", "2026-10-22T00:00:00", "2026-10-24T00:00:00",
                 None, None, None, None, "pending", "", "manual")
    board = CalendarBoard()
    board.resize(450 if mode == "week" else 900, 650)
    board.set_data(date(2026, 10, 22), mode, "current", [item], {1: {"all_day": all_day}})
    board.show()
    app.processEvents()
    if mode == "week":
        board.scroll.horizontalScrollBar().setValue(90)
        app.processEvents()
    canvas = board.month if mode == "month" else board.header if all_day else board.grid
    requests = []
    board.context_requested.connect(lambda event_id, position: requests.append((event_id, position)))
    rect = canvas.hits[-1][0]
    point = rect.center().toPoint()
    if canvas is board.header:
        point -= QPoint(board.scroll.horizontalScrollBar().value(), 0)
    global_pos = canvas.mapToGlobal(point)
    event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, point, global_pos)
    app.sendEvent(canvas, event)
    assert requests == [(1, global_pos)]
    assert board.clicked_day == date(2026, 10, 22 if mode == "day" else 23)
    assert event.isAccepted()
    requests.clear()
    app.sendEvent(canvas, QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(1, 1), canvas.mapToGlobal(QPoint(1, 1))))
    assert not requests
    board.close()


def choose_menu_action(app, invoke, status=None):
    """Click the real popup; always close it even if inspecting it raises."""
    from PySide6.QtCore import QTimer, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QMenu

    result = {}
    def choose():
        menu = app.activePopupWidget()
        try:
            assert isinstance(menu, QMenu)
            actions = [action for action in menu.actions() if action.isCheckable()]
            result["statuses"] = {action.data(): action.text() for action in actions}
            result["checked"] = [action.data() for action in actions if action.isChecked()]
            menu.grab()  # Exercise custom painting before activating a native action.
            if status is not None:
                action = next(action for action in actions if action.data() == status)
                QTest.mouseClick(menu, Qt.MouseButton.LeftButton, pos=menu.actionGeometry(action).center())
        except Exception as exc:
            result["error"] = exc
        finally:
            if menu is not None:
                menu.close()
    QTimer.singleShot(0, choose)
    invoke()
    assert "error" not in result, result.get("error")
    assert "statuses" in result
    return result


@pytest.mark.parametrize("source", ["manual", "caldav"])
@pytest.mark.parametrize("has_fact", [False, True])
def test_menu_changes_only_target_status_and_refreshes_ui_and_audit(app, tmp_path, source, has_fact):
    from PySide6.QtCore import QDate, QPoint
    from director_control.mail_calendar import CalendarConfig, parse_calendars
    from director_control.storage import Store, STATUSES
    from director_control.ui import MainWindow

    store = Store(tmp_path / "menu.db")
    if source == "caldav":
        config = CalendarConfig("https://calendar.mail.ru/principals/test/calendars/context/", "test@example.test")
        snapshot = parse_calendars(["BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:context-test\r\n"
            "DTSTART:20261022T090000\r\nDTEND:20261022T100000\r\nSUMMARY:Mail event\r\n"
            "END:VEVENT\r\nEND:VCALENDAR\r\n"], config, date(2026, 10, 22), date(2026, 10, 24))
        store.apply_calendar_snapshot(snapshot)
        target = store.daily_events("2026-10-22")[0].id
    else:
        target = store.create_event("Ручное событие", "Работа", "2026-10-22T09:00:00", "2026-10-22T10:00:00")
    other = store.create_event("Другое событие", "Работа", "2026-10-22T11:00:00", "2026-10-22T12:00:00")
    store.freeze_day("2026-10-22")
    store.update_event(target, note="Локальный комментарий", category="Работа", **(
        {"actual_start": "2026-10-22T09:05:00", "actual_end": "2026-10-22T10:15:00"} if has_fact else {}))
    before, untouched = store.get_event(target), store.get_event(other)
    window = MainWindow(store)
    window.date_input.setDate(QDate(2026, 10, 22))
    window.show()
    app.processEvents()
    previous = "pending"
    for status in ("done", "partial", "cancelled", "moved", "pending"):
        window.select_event(other)
        count = len(store.audit_log())
        menu = choose_menu_action(app, lambda: window.show_event_context_menu(target, window.mapToGlobal(QPoint(430, 350))), status)
        assert menu["statuses"] == STATUSES and menu["checked"] == [previous]
        event = store.get_event(target)
        assert event.status == status and replace(event, status=before.status) == before
        assert store.get_event(other) == untouched
        assert window.selected_event_id() == target
        assert window.inspector.status.text() == STATUSES[status]
        expected_label = STATUSES[status] + (" · отклонение" if has_fact and status == "done" else "")
        assert window.table.item(window.row_ids.index(target), 5).text() == expected_label
        assert window.cards["done"].value.text() == ("1" if status == "done" else "0")
        assert len(store.audit_log()) == count + 1
        last = store.audit_log()[0]
        assert last["event_id"] == target and set(json.loads(last["details"])) == {"status"}
        previous = status
    if source == "caldav":
        assert store.calendar_info()[target]["local_status"] == 1
        cancelled = replace(snapshot, events=tuple(replace(item, cancelled=True) for item in snapshot.events))
        store.apply_calendar_snapshot(cancelled)
        assert store.get_event(target).status == "pending"
    window.close()


def test_dismissal_and_choosing_current_status_do_not_create_changes(app, tmp_path):
    from PySide6.QtCore import QDate, QPoint
    from director_control.storage import Store
    from director_control.ui import MainWindow

    store = Store(tmp_path / "unchanged.db")
    target = store.create_event("Событие", "Работа", "2026-10-22T09:00:00", "2026-10-22T10:00:00")
    before = store.get_event(target)
    count = len(store.audit_log())
    window = MainWindow(store)
    window.date_input.setDate(QDate(2026, 10, 22))
    window.show()
    app.processEvents()
    for status in (None, "pending"):
        choose_menu_action(app, lambda: window.show_event_context_menu(target, window.mapToGlobal(QPoint(430, 350))), status)
        assert store.get_event(target) == before and len(store.audit_log()) == count
    window.close()


def test_list_context_menu_uses_clicked_row_instead_of_previous_selection(app, tmp_path, monkeypatch):
    from PySide6.QtCore import QDate, QPoint
    from director_control.storage import Store
    from director_control.ui import MainWindow

    store = Store(tmp_path / "list-menu.db")
    first = store.create_event("Первое", "Работа", "2026-10-22T09:00:00", "2026-10-22T10:00:00")
    second = store.create_event("Второе", "Работа", "2026-10-22T11:00:00", "2026-10-22T12:00:00")
    window = MainWindow(store)
    window.date_input.setDate(QDate(2026, 10, 22))
    window.set_view("agenda")
    window.show()
    app.processEvents()
    window.select_event(first)
    point = window.table.visualItemRect(window.table.item(window.row_ids.index(second), 0)).center()
    choose_menu_action(app, lambda: window.table.customContextMenuRequested.emit(point), "partial")
    assert store.get_event(first).status == "pending" and store.get_event(second).status == "partial"
    assert window.selected_event_id() == second
    calls = []
    monkeypatch.setattr(window, "show_event_context_menu", lambda *args: calls.append(args))
    window.show_table_context_menu(QPoint(1, window.table.viewport().height() - 2))
    assert not calls
    window.close()


@pytest.mark.parametrize("category", ["Работа", "Встречи"])
def test_menu_row_and_hover_colors_match_calendar_for_every_status(app, category):
    from PySide6.QtGui import QActionGroup
    from director_control.calendar_view import color_for
    from director_control.status_menu import EventStatusMenu
    from director_control.storage import Event, STATUSES
    from director_control.theme import STYLE

    item = Event(1, "Цвет меню", category, "2026-10-22T09:00:00", "2026-10-22T10:00:00",
                 None, None, None, None, "partial", "", "manual")
    menu = EventStatusMenu(item)
    menu.setStyleSheet(STYLE)
    group = QActionGroup(menu)
    for status, label in STATUSES.items():
        action = menu.addAction(label)
        action.setData(status)
        action.setCheckable(True)
        group.addAction(action)
        action.setChecked(status == item.status)
    menu.show()
    app.processEvents()
    menu.setActiveAction(None)
    image = menu.grab().toImage()
    for action in menu.actions():
        # Compare painted pixels to the actual calendar color after that change.
        accent, fill = color_for(replace(item, status=action.data()))
        bounds = menu.actionGeometry(action)
        x, y = bounds.right() - 12, bounds.center().y()
        assert image.pixelColor(x, y).rgb() == fill.rgb()
        foreground = accent.darker(125)
        def near_foreground(pixel):
            # Font antialiasing blends the ink with the pastel background.
            return max(abs(pixel.red() - foreground.red()), abs(pixel.green() - foreground.green()),
                       abs(pixel.blue() - foreground.blue())) <= 16
        assert any(near_foreground(image.pixelColor(px, py))
                   for px in range(bounds.left() + 40, bounds.right() - 16)
                   for py in range(bounds.top() + 3, bounds.bottom() - 3))
        menu.setActiveAction(action)
        hovered = menu.grab().toImage()
        assert hovered.pixelColor(x, y).rgb() == fill.darker(105).rgb()
        menu.setActiveAction(None)
    assert [action.data() for action in menu.actions() if action.isChecked()] == ["partial"]
    menu.close()
