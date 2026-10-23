"""Shared date-picker behavior in the sidebar, calendar toolbar and event card."""
import os

import pytest


@pytest.fixture(scope="module")
def app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from director_control.theme import STYLE

    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    return app


def open_popup(app, control):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    QTest.mouseClick(control, Qt.MouseButton.LeftButton,
                     pos=QPoint(control.width() - 10, control.height() // 2))
    app.processEvents()
    calendar = control.calendarWidget()
    assert calendar.isVisible()
    assert not calendar.isNavigationBarVisible()
    return calendar


def click_day(app, calendar, day):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    QTest.mouseClick(calendar._view.viewport(), Qt.MouseButton.LeftButton,
                     pos=calendar._cell_rects[day].center())
    app.processEvents()


def test_toolbar_selection_and_sidebar_keyboard_stay_in_sync(app, tmp_path):
    from PySide6.QtCore import QDate, Qt
    from PySide6.QtTest import QTest
    from director_control.mini_calendar import MiniCalendar
    from director_control.storage import Store
    from director_control.ui import MainWindow
    from tests.helpers import seed_event

    store = Store(tmp_path / "toolbar.db")
    target = seed_event(store, "Выбранный день", "Работа", "2026-10-26T09:00:00", "2026-10-26T10:00:00")
    window = MainWindow(store)
    window.resize(1480, 930)
    window.date_input.setDate(QDate(2026, 10, 23))
    window.show()
    app.processEvents()
    calendar = open_popup(app, window.date_input)
    assert isinstance(calendar, MiniCalendar) and isinstance(window.mini, MiniCalendar)
    click_day(app, calendar, QDate(2026, 10, 26))
    assert not calendar.isVisible()
    assert window.selected_day() == "2026-10-26"
    assert window.mini.selectedDate() == QDate(2026, 10, 26)
    assert window.row_ids == [target]
    window.mini._view.setFocus()
    QTest.keyClick(window.mini._view, Qt.Key.Key_Right)
    QTest.keyClick(window.mini._view, Qt.Key.Key_Return)
    app.processEvents()
    assert window.selected_day() == "2026-10-27"
    assert window.date_input.calendarWidget().selectedDate() == QDate(2026, 10, 27)
    window.close()


@pytest.mark.parametrize("field,day", [("fact_start", 22), ("fact_end", 24)])
def test_event_pickers_preserve_time_and_save_only_local_fact(app, tmp_path, field, day):
    from PySide6.QtCore import QDate
    from PySide6.QtWidgets import QDateTimeEdit
    from director_control.mini_calendar import MiniCalendar
    from director_control.storage import Store
    from director_control.ui import EventDialog
    from tests.helpers import seed_event

    store = Store(tmp_path / f"{field}.db")
    event_id = seed_event(store, "Встреча", "Работа", "2026-10-23T09:10:15", "2026-10-23T10:00:45")
    store.freeze_day("2026-10-23")
    before = store.get_event(event_id)
    dialog = EventDialog(store, before)
    assert len(dialog.findChildren(QDateTimeEdit)) == 4
    assert all(isinstance(control.calendarWidget(), MiniCalendar)
               for control in dialog.findChildren(QDateTimeEdit))
    assert not dialog.start_input.isEnabled() and not dialog.end_input.isEnabled()
    dialog.fact_checkbox.setChecked(True)
    dialog.show()
    app.processEvents()
    control = getattr(dialog, field)
    original_time = control.time()
    calendar = open_popup(app, control)
    click_day(app, calendar, QDate(2026, 10, day))
    assert not calendar.isVisible()
    assert control.date() == QDate(2026, 10, day) and control.time() == original_time
    dialog.save()
    event = store.get_event(event_id)
    actual = event.actual_start if field == "fact_start" else event.actual_end
    assert actual == control.dateTime().toString("yyyy-MM-ddTHH:mm:ss")
    assert (event.title, event.current_start, event.current_end, event.baseline_start, event.baseline_end) == (
        before.title, before.current_start, before.current_end, before.baseline_start, before.baseline_end)
    dialog.close()


def date_control(app):
    from PySide6.QtCore import QDate
    from PySide6.QtWidgets import QDateEdit
    from director_control.mini_calendar import MiniCalendar

    control = QDateEdit(QDate(2026, 10, 23))
    control.setDisplayFormat("dd.MM.yyyy")
    control.setCalendarPopup(True)
    control.setCalendarWidget(MiniCalendar(control))
    control.resize(180, 40)
    control.show()
    app.processEvents()
    return control


def test_keyboard_escape_enter_and_date_limits(app):
    from PySide6.QtCore import QDate, Qt
    from PySide6.QtTest import QTest

    control = date_control(app)
    control.setDateRange(QDate(2026, 10, 22), QDate(2026, 10, 24))
    calendar = open_popup(app, control)
    assert not calendar.previous.isEnabled() and not calendar.next.isEnabled()
    QTest.keyClick(calendar._view, Qt.Key.Key_Right)
    # Native Qt date edits apply keyboard selection immediately; Escape closes the popup.
    assert control.date() == QDate(2026, 10, 24)
    QTest.keyClick(calendar._view, Qt.Key.Key_Escape)
    app.processEvents()
    assert not calendar.isVisible() and control.date() == QDate(2026, 10, 24)
    control.setDate(QDate(2026, 10, 23))
    calendar = open_popup(app, control)
    QTest.keyClick(calendar._view, Qt.Key.Key_Right)
    QTest.keyClick(calendar._view, Qt.Key.Key_Right)
    QTest.keyClick(calendar._view, Qt.Key.Key_Return)
    app.processEvents()
    assert not calendar.isVisible() and control.date() == QDate(2026, 10, 24)
    control.close()


@pytest.mark.filterwarnings("error::pytest.PytestUnraisableExceptionWarning")
def test_date_edit_can_be_destroyed_with_popup_open(app):
    from PySide6.QtCore import QCoreApplication, QEvent
    from shiboken6 import isValid

    control = date_control(app)
    calendar = open_popup(app, control)
    control.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    assert not isValid(control) and not isValid(calendar)


def test_custom_month_menu_navigates_without_changing_date_until_day_is_chosen(app):
    from PySide6.QtCore import QDate, Qt, QTimer
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QMenu

    control = date_control(app)
    calendar = open_popup(app, control)
    result = {}

    def choose_month():
        menu = app.activePopupWidget()
        result["menu"] = isinstance(menu, QMenu) and menu.objectName() == "MiniCalendarMenu"
        if result["menu"]:
            action = next(action for action in menu.actions() if action.data() == 11)
            QTest.mouseClick(menu, Qt.MouseButton.LeftButton, pos=menu.actionGeometry(action).center())

    QTimer.singleShot(0, choose_month)
    calendar.month_button.click()
    app.processEvents()
    assert result["menu"] and calendar.isVisible()
    assert calendar.monthShown() == 11 and "Ноябрь" in calendar.month_button.text()
    assert control.date() == QDate(2026, 10, 23)
    click_day(app, calendar, QDate(2026, 11, 5))
    assert control.date() == QDate(2026, 11, 5)
    control.close()


@pytest.mark.parametrize("accept", [True, False])
def test_year_dialog_restores_popup_for_day_selection(app, accept):
    from PySide6.QtCore import QDate, QTimer
    from PySide6.QtWidgets import QInputDialog

    control = date_control(app)
    calendar = open_popup(app, control)
    result = {}

    def choose_year():
        dialog = app.activeModalWidget()
        result["dialog"] = isinstance(dialog, QInputDialog)
        if result["dialog"]:
            dialog.setIntValue(2027)
            dialog.accept() if accept else dialog.reject()

    QTimer.singleShot(0, choose_year)
    calendar._choose_year()
    app.processEvents()
    year = 2027 if accept else 2026
    assert result["dialog"] and calendar.isVisible()
    assert calendar.yearShown() == year and calendar.monthShown() == 10
    assert control.date() == QDate(2026, 10, 23)
    click_day(app, calendar, QDate(year, 10, 25))
    assert control.date() == QDate(year, 10, 25) and not calendar.isVisible()
    control.close()
