"""Live theme changes, saved preferences and custom-painted surfaces."""
import os
import gc
from dataclasses import replace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QDate, QEvent, QPoint, Qt
from PySide6.QtGui import QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from director_control.calendar_view import color_for, event_foreground, event_hover
from director_control.status_menu import EventStatusMenu
from director_control.storage import STATUSES, Store
from director_control.theme import DARK, LIGHT, apply_theme, color, current_theme
from director_control.ui import EventDialog, MainWindow
from tests.helpers import seed_event


@pytest.fixture
def app():
    gc.collect()
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    apply_theme("light")
    yield app
    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    apply_theme("light")
    app.processEvents()


def make_window(tmp_path):
    store = Store(tmp_path / "theme.db")
    eid = seed_event(store, "Совещание", "Работа", "2026-10-22T09:00:00", "2026-10-22T10:00:00")
    store.update_event(eid, status="partial", note="Обсудить бюджет")
    window = MainWindow(store)
    window.date_input.setDate(QDate(2026, 10, 22))
    window.select_event(eid)
    return store, eid, window


@pytest.mark.parametrize('theme', ['light', 'dark'])
@pytest.mark.parametrize('mode', ['day', 'week', 'month'])
def test_empty_frozen_day_background_survives_filters_and_reload(app, tmp_path, theme, mode):
    from datetime import date
    apply_theme(theme)
    store = Store(tmp_path / 'frozen-background.db')
    window = MainWindow(store)
    apply_theme(theme)
    window.date_input.setDate(QDate(2026, 10, 22))
    window.mode = mode
    window.resize(1300, 900)
    window.show()
    window.reload()
    app.processEvents()
    board = window.calendar
    day = date(2026, 10, 22)

    def background():
        if mode == 'month':
            index = board.days.index(day)
            width, height = board.month.width() / 7, (board.month.height() - 28) / 6
            return board.month.grab().toImage().pixelColor(
                int((index % 7 + .5) * width), int(28 + (index // 7 + .7) * height))
        _, left, width = next(column for column in board.time_columns() if column[0] == day)
        return board.grid.grab().toImage().pixelColor(int(left + width / 2), 20)

    before = background()
    store.freeze_day(day.isoformat())  # No events: fixation itself must drive the background.
    window.search.setText('no matching events')
    window.reload()
    app.processEvents()
    assert board.frozen_days == {day}
    assert background() == color('frozen_day') and background() != before
    window.reload()
    assert board.frozen_days == {day}
    window.close()


def test_toggle_applies_immediately_and_persists_without_changing_schedule(app, tmp_path):
    store, eid, window = make_window(tmp_path)
    before = store.get_event(eid)
    history = store.audit_log()
    window.set_view("agenda")
    window.search.setText("Совещание")
    window.tabs.setCurrentIndex(2)
    window.show()
    app.processEvents()
    QTest.mouseClick(window.theme_toggle, Qt.MouseButton.LeftButton)
    app.processEvents()
    assert current_theme() == "dark"
    assert store.get_setting("ui_theme") == "dark"
    assert window.theme_toggle.text() == "Светлая тема"
    assert window.selected_day() == "2026-10-22"
    assert window.mode == "agenda" and window.tabs.currentIndex() == 2
    assert window.search.text() == "Совещание" and window._selected_id == eid
    assert window.table.item(0, 5).foreground().color() == color_for(before)[0]
    assert store.get_event(eid) == before and store.audit_log() == history
    window.close()

    # Recreate the application window with a fresh connection to the saved DB.
    apply_theme("light")
    restored = MainWindow(Store(store.path))
    assert current_theme() == "dark"
    assert restored.theme_toggle.text() == "Светлая тема"
    restored.theme_toggle.click()
    assert current_theme() == "light"
    assert store.get_setting("ui_theme") == "light"
    assert restored.theme_toggle.text() == "Тёмная тема"


def test_unknown_saved_theme_falls_back_to_light(app, tmp_path):
    store = Store(tmp_path / "unknown.db")
    store.set_setting("ui_theme", "unknown")
    apply_theme("dark")
    window = MainWindow(store)
    assert current_theme() == "light"
    assert window.theme_toggle.text() == "Тёмная тема"


@pytest.mark.parametrize("mode", ["day", "week", "month"])
def test_dark_calendar_surfaces_and_existing_mini_calendar_repaint(app, tmp_path, mode):
    _, _, window = make_window(tmp_path)
    window.resize(1450, 930)
    window.set_view(mode)
    window.show()
    app.processEvents()
    light = window.mini.grab().toImage().pixelColor(2, 2)
    assert light == color("surface")
    window.theme_toggle.click()
    app.processEvents()
    assert window.mini.grab().toImage().pixelColor(2, 2) == color("surface")
    assert light != color("surface")
    canvas = window.calendar.month if mode == "month" else window.calendar.grid
    assert canvas.grab().toImage().pixelColor(2, 2) == color("surface")
    assert window.mini.weekdayTextFormat(Qt.DayOfWeek.Monday).foreground().color() == color("mini_header")


def test_new_dialog_and_date_popup_inherit_dark_theme_and_toggle_with_one_click(app, tmp_path):
    store, eid, window = make_window(tmp_path)
    window.show()
    window.theme_toggle.click()
    dialog = EventDialog(store, store.get_event(eid), window)
    dialog.show()
    dialog.fact_checkbox.setChecked(True)
    app.processEvents()
    palette = dialog.note_input.palette()
    assert palette.color(QPalette.ColorRole.Text).lightness() > 180
    assert palette.color(QPalette.ColorRole.Base).lightness() < 80
    assert dialog.grab().toImage().pixelColor(4, 4) == color("surface")
    picker = dialog.fact_start._date_picker
    QTest.mouseClick(dialog.fact_start.lineEdit(), Qt.MouseButton.LeftButton, pos=QPoint(8, 10))
    app.processEvents()
    assert picker.popup.isVisible()
    assert picker.calendar.graphicsEffect().color().alpha() == 110
    assert picker.calendar._view.viewport().grab().toImage().pixelColor(2, 2).lightness() < 100
    QTest.mouseClick(dialog.fact_start.lineEdit(), Qt.MouseButton.LeftButton, pos=QPoint(8, 10))
    app.processEvents()
    assert not picker.popup.isVisible()
    assert app.overrideCursor() is None


@pytest.mark.parametrize("status", list(STATUSES))
def test_dark_menu_uses_calendar_status_colors_and_legible_foreground(app, tmp_path, status):
    store, eid, window = make_window(tmp_path)
    window.theme_toggle.click()
    event = replace(store.get_event(eid), status=status)
    accent, fill = color_for(event)
    assert accent.lightness() > fill.lightness() + 70
    assert event_foreground(accent) == accent
    menu = EventStatusMenu(event, window)
    action = menu.addAction(STATUSES[status])
    action.setData(status)
    menu.show()
    app.processEvents()
    bounds = menu.actionGeometry(action)
    point = QPoint(bounds.right() - 9, bounds.center().y())
    assert menu.grab().toImage().pixelColor(point) == fill
    menu.setActiveAction(action)
    app.processEvents()
    # QColor's HSV adjustment has 16-bit precision; screenshots have 8-bit RGB.
    assert menu.grab().toImage().pixelColor(point).rgb() == event_hover(fill).rgb()


def test_dark_text_tokens_have_accessible_contrast_on_surfaces(app):
    def luminance(hex_color):
        values = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        values = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in values]
        return sum(v * weight for v, weight in zip(values, (0.2126, 0.7152, 0.0722)))

    assert LIGHT.keys() == DARK.keys()
    for token in ("text", "muted", "subtle", "accent", "calendar_text", "calendar_muted", "mini_text", "mini_header"):
        for background in ("surface", "background"):
            assert (luminance(DARK[token]) + .05) / (luminance(DARK[background]) + .05) >= 4.5
