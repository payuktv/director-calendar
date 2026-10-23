from tests.helpers import seed_event, source_update
from datetime import date

import pytest

from director_control.calendar_view import Block, layout_overlaps, period_days, split_blocks
from director_control.storage import Event, Store


def meeting(index=1, start="2026-10-22T09:00:00", end="2026-10-22T10:00:00", **fields):
    data = dict(id=index, title="Событие", category="Работа", current_start=start, current_end=end,
                baseline_start=None, baseline_end=None, actual_start=None, actual_end=None,
                status="pending", note="", source="caldav")
    data.update(fields)
    return Event(**data)


def test_periods_use_monday_and_handle_year_boundaries():
    week = period_days(date(2027, 1, 1), "week")
    assert week[0] == date(2026, 12, 28) and week[-1] == date(2027, 1, 3)
    month = period_days(date(2026, 10, 22), "month")
    assert len(month) == 42 and month[0] == date(2026, 9, 28) and month[-1] == date(2026, 11, 8)


def test_overlaps_have_distinct_lanes_and_adjacent_events_reuse_lane():
    day = date(2026, 10, 22)
    blocks = [Block(meeting(i), day, start, end) for i, start, end in (
        (1, 540, 720), (2, 600, 660), (3, 660, 720), (4, 720, 780))]
    result = {block.event.id: block for block in layout_overlaps(blocks)}
    assert result[1].lanes == result[2].lanes == result[3].lanes == 2
    assert result[1].lane != result[2].lane
    assert result[2].lane == result[3].lane
    assert result[4].lanes == 1 and result[4].lane == 0


def test_cross_midnight_events_are_clipped_per_day():
    item = meeting(start="2026-10-22T23:30:00", end="2026-10-23T01:00:00")
    days = [date(2026, 10, 22), date(2026, 10, 23)]
    blocks, _ = split_blocks([item], days, "current", {})
    assert (blocks[days[0]][0].start, blocks[days[0]][0].end) == (1410, 1440)
    assert (blocks[days[1]][0].start, blocks[days[1]][0].end) == (0, 60)


def test_layers_and_all_day_flags_are_independent():
    days = [date(2026, 10, 22), date(2026, 10, 23), date(2026, 10, 24)]
    item = meeting(start="2026-10-23T00:00:00", end="2026-10-24T00:00:00",
                   baseline_start="2026-10-22T00:00:00", baseline_end="2026-10-23T00:00:00",
                   actual_start="2026-10-24T11:00:00", actual_end="2026-10-24T12:00:00")
    metadata = {1: {"all_day": 1, "baseline_all_day": 1}}
    current, current_all = split_blocks([item], days, "current", metadata)
    original, original_all = split_blocks([item], days, "baseline", metadata)
    actual, actual_all = split_blocks([item], days, "actual", metadata)
    assert not any(current.values()) and current_all[days[1]] == [item]
    assert not any(original.values()) and original_all[days[0]] == [item]
    assert actual[days[2]][0].start == 660 and not any(actual_all.values())


def test_missing_fact_does_not_create_a_calendar_block():
    days = [date(2026, 10, 22)]
    blocks, _ = split_blocks([meeting(status="done")], days, "actual", {})
    assert not blocks[days[0]]


def test_period_query_includes_actual_time_outside_both_plans(tmp_path):
    store = Store(tmp_path / "events.db")
    eid = seed_event(store, "Перенос", "Работа", "2026-10-22T09:00:00", "2026-10-22T10:00:00")
    store.freeze_day("2026-10-22")
    source_update(store, eid, current_start="2026-10-23T09:00:00", current_end="2026-10-23T10:00:00",
                       actual_start="2026-10-24T11:00:00", actual_end="2026-10-24T12:00:00")
    assert [e.id for e in store.events_between("2026-10-24T00:00:00", "2026-10-25T00:00:00")] == [eid]
    assert store.events_between("2026-10-24T12:00:00", "2026-10-25T00:00:00") == []


def test_timeline_selection_activation_and_empty_slot():
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from director_control.calendar_view import CalendarBoard, GUTTER

    app = QApplication.instance() or QApplication([])
    board = CalendarBoard()
    board.resize(900, 650)
    board.set_data(date(2026, 10, 22), "day", "current", [meeting()], {})
    board.show()
    app.processEvents()
    selected, opened = [], []
    board.selected.connect(selected.append)
    board.activated.connect(opened.append)
    rect, _ = board.grid.hits[0]
    QTest.mouseClick(board.grid, Qt.MouseButton.LeftButton, pos=rect.center().toPoint())
    QTest.mouseDClick(board.grid, Qt.MouseButton.LeftButton, pos=rect.center().toPoint())
    QTest.mouseDClick(board.grid, Qt.MouseButton.LeftButton,
                     pos=QPoint(GUTTER + 100, int(11.25 * board.hour_height)))
    assert selected == [1] and opened == [1]
    assert not hasattr(board, "slot_requested")
    board.close()


def test_month_grid_does_not_fill_later_cells_with_previous_event_color():
    from PySide6.QtWidgets import QApplication
    from director_control.calendar_view import CalendarBoard

    app = QApplication.instance() or QApplication([])
    board = CalendarBoard()
    board.resize(900, 650)
    board.set_data(date(2026, 10, 22), "month", "current", [meeting()], {})
    board.show()
    app.processEvents()
    image = board.month.grab().toImage()
    color = image.pixelColor(image.width() - 30, image.height() - 30)
    assert min(color.red(), color.green(), color.blue()) > 240
    board.close()


def test_last_minute_event_has_positive_clickable_geometry():
    from PySide6.QtWidgets import QApplication
    from director_control.calendar_view import CalendarBoard

    app = QApplication.instance() or QApplication([])
    board = CalendarBoard()
    board.resize(900, 650)
    item = meeting(start="2026-10-22T23:59:30", end="2026-10-23T00:00:00")
    board.set_data(date(2026, 10, 22), "day", "current", [item], {})
    board.show()
    app.processEvents()
    assert board.grid.hits[0][0].height() > 0
    board.close()


def test_month_overflow_opens_accessible_day_list():
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from director_control.calendar_view import CalendarBoard

    app = QApplication.instance() or QApplication([])
    board = CalendarBoard()
    board.resize(900, 650)
    board.set_data(date(2026, 10, 22), "month", "current", [meeting(index=i) for i in range(1, 7)], {})
    chosen, opened = [], []
    board.date_selected.connect(chosen.append)
    board.agenda_requested.connect(lambda: opened.append(True))
    board.show()
    app.processEvents()
    rect, _ = board.month.more[0]
    QTest.mouseClick(board.month, Qt.MouseButton.LeftButton, pos=rect.center().toPoint())
    assert chosen == [date(2026, 10, 22)] and opened == [True]
    board.close()


def test_wrapped_title_uses_full_height_and_elides_the_last_complete_line():
    from PySide6.QtGui import QFontMetricsF
    from PySide6.QtWidgets import QApplication
    from director_control.calendar_view import fit_wrapped_text, font

    _app = QApplication.instance() or QApplication([])
    face = font(12)
    title = "Обсуждение графика поставок и согласование бюджета нового проекта"
    short = fit_wrapped_text(title, face, 85, 34)
    tall = fit_wrapped_text(title, face, 85, 180)
    assert short.truncated and short.lines[-1].endswith("…")
    assert len(short.lines) * short.line_height <= 34
    assert not tall.truncated and len(tall.lines) > 3
    assert "".join(tall.lines).replace(" ", "") == title.replace(" ", "")
    metrics = QFontMetricsF(face)
    assert all(metrics.horizontalAdvance(line) <= 85 for line in short.lines + tall.lines)


def test_long_words_and_emoji_wrap_without_losing_characters():
    from PySide6.QtGui import QFontMetricsF
    from PySide6.QtWidgets import QApplication
    from director_control.calendar_view import fit_wrapped_text, font

    _app = QApplication.instance() or QApplication([])
    face = font(12)
    title = "Сверхдлинноеназваниемероприятия📅Согласованиепоставки"
    fitted = fit_wrapped_text(title, face, 48, 500)
    assert not fitted.truncated and "".join(fitted.lines) == title
    assert all(QFontMetricsF(face).horizontalAdvance(line) <= 48 for line in fitted.lines)


@pytest.mark.parametrize("width,height", [(90, 24), (90, 51), (42, 100), (90, 180), (9, 1)])
def test_event_text_stays_inside_short_narrow_and_tall_cards(width, height, monkeypatch):
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtWidgets import QApplication
    from director_control import calendar_view

    _app = QApplication.instance() or QApplication([])
    board = calendar_view.CalendarBoard()
    item = meeting(title="Согласование технического задания и графика поставок оборудования")
    image = QImage(160, 240, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    card = QRectF(20, 20, width, height)
    drawn = []
    real_text = calendar_view.text

    def record(painter, rect, value, *args, **kwargs):
        used = real_text(painter, rect, value, *args, **kwargs)
        drawn.append((QRectF(rect), value, used))
        return used

    monkeypatch.setattr(calendar_view, "text", record)
    board.grid.draw_chip(painter, card, item)
    painter.end()
    visible = [(rect, value, used) for rect, value, used in drawn if used]
    assert all(card.contains(QRectF(rect.x(), rect.y(), rect.width(), used)) for rect, _, used in visible)
    for (rect, _, used), (following, _, _) in zip(visible, visible[1:]):
        assert rect.y() + used <= following.y()
    if height == 24:
        assert [value for _, value, _ in visible] == [item.title]
    if height == 180:
        title_rect = next(rect for rect, value, _ in visible if value == item.title)
        assert title_rect.height() > 40
    for y in range(image.height()):
        for x in range(image.width()):
            if x < 20 or x >= 20 + width or y < 20 or y >= 20 + height:
                assert image.pixelColor(x, y) == Qt.GlobalColor.white
    board.close()


def test_full_event_title_remains_available_in_hover_tooltip():
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QHelpEvent
    from PySide6.QtWidgets import QApplication, QToolTip
    from director_control.calendar_view import CalendarBoard

    app = QApplication.instance() or QApplication([])
    board = CalendarBoard()
    title = "Согласование графика поставок и бюджета проекта — полное название"
    item = meeting(title=title, end="2026-10-22T09:15:00")
    board.resize(700, 600)
    board.set_data(date(2026, 10, 22), "week", "current", [item], {})
    board.show()
    app.processEvents()
    point = board.grid.hits[0][0].center().toPoint()
    QApplication.sendEvent(board.grid, QHelpEvent(QEvent.Type.ToolTip, point, board.grid.mapToGlobal(point)))
    assert title in QToolTip.text() and "09:00" in QToolTip.text() and "09:15" in QToolTip.text()
    QToolTip.hideText()
    board.close()
