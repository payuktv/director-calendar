"""A focused week column shares its wider geometry with events and clicks."""
from datetime import date, timedelta

import pytest
from PySide6.QtCore import QDate, QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QContextMenuEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from director_control.calendar_view import CalendarBoard, GUTTER
from director_control.storage import Store
from director_control.ui import MainWindow
from tests.helpers import seed_event
from tests.test_calendar_view import meeting


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def board(app):
    board = CalendarBoard()
    yield board
    board.close()
    board.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.mark.parametrize("focus_index", [0, 3, 6])
@pytest.mark.parametrize("width", [450, 1100])
def test_focused_column_ratio_and_header_event_alignment(app, board, focus_index, width):
    monday = date(2026, 10, 19)
    days = [monday + timedelta(days=i) for i in range(7)]
    events, metadata = [], {}
    for i, day in enumerate(days):
        events.append(meeting(i + 1, start=f"{day}T09:00:00", end=f"{day}T10:00:00"))
        events.append(meeting(i + 11, start=f"{day}T00:00:00", end=f"{day + timedelta(days=1)}T00:00:00"))
        metadata[i + 11] = {"all_day": True}
    board.resize(width, 650)
    board.set_data(days[focus_index], "week", "current", events, metadata)
    board.show()
    app.processEvents()
    columns = board.time_columns()
    widths = [column[2] for column in columns]
    normal = widths[(focus_index + 1) % 7]
    assert widths[focus_index] == pytest.approx(normal * 1.5)
    assert all(w == pytest.approx(normal) for i, w in enumerate(widths) if i != focus_index)
    assert columns[0][1] == GUTTER
    assert columns[-1][1] + widths[-1] == pytest.approx(board.grid.width())
    timed = {event.id: rect for rect, event in board.grid.hits}
    all_day = {event.id: rect for rect, event in board.header.hits}
    for i, (day, left, column_width) in enumerate(columns):
        assert timed[i + 1].left() == all_day[i + 11].left() == pytest.approx(left + 5)
        assert timed[i + 1].right() <= left + column_width
        assert all_day[i + 11].right() == pytest.approx(left + column_width - 5)
        assert board.grid.slot(QPointF(left + column_width - 1, 0))[0] == day
        assert board.header.context_day(QPointF(left + column_width - 1, 0)) == day


@pytest.fixture
def window(app, tmp_path):
    store = Store(tmp_path / "focus.db")
    ids = [seed_event(store, f"Встреча {day}", "Работа", f"2026-10-{day}T09:00:00",
                      f"2026-10-{day}T10:00:00") for day in range(19, 26)]
    all_day = seed_event(store, "На всю неделю", "Работа", "2026-10-19T00:00:00", "2026-10-26T00:00:00")
    with store._connect() as con:
        con.execute("UPDATE calendar_events SET all_day=1 WHERE event_id=?", (all_day,))
    window = MainWindow(store)
    window.resize(1450, 930)
    window.date_input.setDate(QDate(2026, 10, 22))
    window.show()
    app.processEvents()
    yield window, ids, all_day
    window.close()
    window.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_clicks_and_date_controls_move_expansion_without_resizing_calendar(app, window):
    window, _, _ = window
    board = window.calendar
    original_width = board.width()
    _, left, width = board.time_columns()[1]
    QTest.mouseClick(board.header, Qt.MouseButton.LeftButton, pos=QPoint(int(left + width / 2), 35))
    app.processEvents()
    assert window.selected_day() == "2026-10-20"
    assert board.time_columns()[1][2] == pytest.approx(board.time_columns()[0][2] * 1.5)
    # This point would belong to the next day under the old equal-width formula.
    _, left, width = board.time_columns()[1]
    point = QPoint(int(left + width - 2), int(11 * board.hour_height))
    QTest.mouseClick(board.grid, Qt.MouseButton.LeftButton, pos=point)
    assert window.selected_day() == "2026-10-20"
    window.mini.clicked.emit(QDate(2026, 10, 25))
    app.processEvents()
    assert board.focus == date(2026, 10, 25)
    assert board.time_columns()[6][2] == pytest.approx(board.time_columns()[0][2] * 1.5)
    window.date_input.setDate(QDate(2026, 10, 19))
    app.processEvents()
    assert board.time_columns()[0][2] == pytest.approx(board.time_columns()[6][2] * 1.5)
    assert board.width() == original_width


def test_timed_and_multiday_all_day_clicks_focus_the_clicked_day(app, window):
    window, ids, all_day = window
    board = window.calendar
    event_before = window.store.get_event(ids[1])
    history_before = window.store.audit_log()
    rect = next(rect for rect, event in board.grid.hits if event.id == ids[1])
    QTest.mouseClick(board.grid, Qt.MouseButton.LeftButton, pos=rect.center().toPoint())
    app.processEvents()
    assert window._selected_id == ids[1] and window.selected_day() == "2026-10-20"
    sunday = board.time_columns()[-1]
    point = QPoint(int(sunday[1] + sunday[2] / 2), 73)
    QTest.mouseClick(board.header, Qt.MouseButton.LeftButton, pos=point)
    app.processEvents()
    assert window._selected_id == all_day and window.selected_day() == "2026-10-25"
    assert window.store.get_event(ids[1]) == event_before
    assert window.store.audit_log() == history_before


def test_double_click_keeps_overlapping_event_target_when_its_column_expands(app, window):
    window, _, _ = window
    first, second = [seed_event(window.store, title, "Работа", "2026-10-25T15:00:00",
                                "2026-10-25T16:00:00") for title in ("Первое", "Второе")]
    window.reload()
    app.processEvents()
    board = window.calendar
    board.activated.disconnect(window.open_event)
    opened = []
    board.activated.connect(opened.append)
    rect = next(rect for rect, event in board.grid.hits if event.id == first)
    point = rect.center().toPoint()
    QTest.mouseClick(board.grid, Qt.MouseButton.LeftButton, pos=point)
    app.processEvents()
    assert window.selected_day() == "2026-10-25" and window._selected_id == first
    assert board.grid.hit(point).id == second
    QTest.mouseDClick(board.grid, Qt.MouseButton.LeftButton, pos=point)
    assert opened == [first]


@pytest.mark.parametrize("canvas_name", ["grid", "header"])
def test_context_menu_hit_testing_keeps_focused_day_with_horizontal_scroll(app, board, canvas_name):
    event = meeting(start="2026-10-19T00:00:00", end="2026-10-26T00:00:00")
    board.resize(450, 650)
    board.set_data(date(2026, 10, 22), "week", "current", [event],
                   {1: {"all_day": canvas_name == "header"}})
    board.show()
    app.processEvents()
    board.scroll.horizontalScrollBar().setValue(90)
    app.processEvents()
    canvas = getattr(board, canvas_name)
    day, left, width = board.time_columns()[3]
    point = QPoint(int(left + width - 8), 73 if canvas_name == "header" else int(9 * board.hour_height))
    if canvas_name == "header":
        point -= QPoint(board.scroll.horizontalScrollBar().value(), 0)
    requests = []
    board.context_requested.connect(lambda eid, pos: requests.append((eid, pos)))
    global_pos = canvas.mapToGlobal(point)
    app.sendEvent(canvas, QContextMenuEvent(QContextMenuEvent.Reason.Mouse, point, global_pos))
    assert requests == [(1, global_pos)]
    assert board.clicked_day == day


def test_single_day_remains_full_width(app, board):
    board.resize(900, 650)
    board.set_data(date(2026, 10, 22), "day", "current", [], {})
    board.show()
    app.processEvents()
    assert board.time_columns() == [(date(2026, 10, 22), GUTTER, board.grid.width() - GUTTER)]
