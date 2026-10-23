"""Wheel gestures scroll forms without editing the field under the pointer."""
import os

import pytest


@pytest.fixture(scope="module")
def app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from director_control.input_wheel import install_input_wheel_guard

    app = QApplication.instance() or QApplication([])
    install_input_wheel_guard(app)
    return app


def wheel(target, angle=-120, pixel=0, horizontal=False):
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import QApplication

    point = target.rect().center()
    event = QWheelEvent(
        QPointF(point), QPointF(target.mapToGlobal(point)),
        QPoint(pixel, 0) if horizontal else QPoint(0, pixel),
        QPoint(angle, 0) if horizontal else QPoint(0, angle),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False,
    )
    QApplication.sendEvent(target, event)


def value(field):
    from PySide6.QtWidgets import QComboBox, QDateTimeEdit, QLineEdit

    if isinstance(field, QComboBox):
        return field.currentIndex(), field.currentText()
    if isinstance(field, QDateTimeEdit):
        return field.dateTime()
    if isinstance(field, QLineEdit):
        return field.text()
    return field.value()


@pytest.mark.parametrize("kind", ["integer", "decimal", "date", "datetime", "time", "list", "editable", "text", "slider", "dial"])
def test_wheel_never_changes_focused_or_unfocused_field_values(app, kind):
    from PySide6.QtCore import QDate, QDateTime, QTime, Qt
    from PySide6.QtWidgets import (
        QComboBox, QDateEdit, QDateTimeEdit, QDial, QDoubleSpinBox, QLineEdit,
        QSlider, QSpinBox, QTimeEdit, QVBoxLayout, QWidget,
    )

    constructors = {"integer": QSpinBox, "decimal": QDoubleSpinBox, "date": QDateEdit,
                    "datetime": QDateTimeEdit, "time": QTimeEdit, "list": QComboBox,
                    "editable": QComboBox, "text": QLineEdit, "slider": QSlider, "dial": QDial}
    window = QWidget()
    layout = QVBoxLayout(window)
    field = constructors[kind]()
    if isinstance(field, QComboBox):
        field.addItems(["Первый", "Второй", "Третий"])
        field.setCurrentIndex(1)
        field.setEditable(kind == "editable")
    elif isinstance(field, QDateTimeEdit):
        field.setDateTime(QDateTime(QDate(2026, 10, 23), QTime(9, 10, 15)))
    elif isinstance(field, QLineEdit):
        field.setText("Комментарий")
    else:
        field.setValue(50)
    layout.addWidget(field)
    other = QLineEdit()
    layout.addWidget(other)
    window.show()
    app.processEvents()
    before = value(field)
    for focused in (False, True):
        (field if focused else other).setFocus(Qt.FocusReason.OtherFocusReason)
        app.processEvents()
        targets = [field]
        if hasattr(field, "lineEdit") and field.lineEdit() is not None:
            targets.append(field.lineEdit())
        for target in targets:
            for delta in (-120, 120):
                wheel(target, angle=delta)
                assert value(field) == before
    window.close()


@pytest.mark.parametrize("horizontal", [False, True])
def test_wheel_over_field_scrolls_its_form_and_keeps_scrollbars_working(app, horizontal):
    from PySide6.QtWidgets import QScrollArea, QSpinBox, QVBoxLayout, QWidget

    area = QScrollArea()
    content = QWidget()
    content.setMinimumSize(900, 1200)
    layout = QVBoxLayout(content)
    field = QSpinBox()
    field.setValue(50)
    layout.addWidget(field)
    layout.addStretch()
    area.setWidget(content)
    area.resize(350, 220)
    area.show()
    app.processEvents()
    bar = area.horizontalScrollBar() if horizontal else area.verticalScrollBar()
    wheel(field, horizontal=horizontal, pixel=-20)
    assert field.value() == 50 and bar.value() > 0
    before = bar.value()
    wheel(bar, horizontal=horizontal)
    assert bar.value() > before and field.value() == 50
    area.close()


def test_open_combo_list_still_scrolls_without_committing_a_selection(app):
    from PySide6.QtWidgets import QComboBox

    combo = QComboBox()
    combo.addItems([f"Категория {index}" for index in range(80)])
    combo.setMaxVisibleItems(5)
    combo.show()
    combo.showPopup()
    app.processEvents()
    view = combo.view()
    before = combo.currentIndex()
    wheel(view.viewport(), angle=-360)
    assert view.verticalScrollBar().value() > 0
    assert combo.currentIndex() == before
    combo.hidePopup()
    combo.close()


def test_application_fields_and_year_dialog_keep_values_but_allow_keyboard_editing(app, tmp_path):
    from PySide6.QtCore import QDate, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QInputDialog, QSpinBox
    from director_control.storage import Store
    from director_control.ui import EventDialog, MainWindow
    from tests.helpers import seed_event

    store = Store(tmp_path / "wheel.db")
    event_id = seed_event(store, "Встреча", "Работа", "2026-10-23T09:10:15", "2026-10-23T10:00:45")
    window = MainWindow(store)
    window.date_input.setDate(QDate(2026, 10, 23))
    dialog = EventDialog(store, store.get_event(event_id))
    dialog.fact_checkbox.setChecked(True)
    year = QInputDialog(window)
    year.setInputMode(QInputDialog.InputMode.IntInput)
    year.setIntRange(2000, 2100)
    year.setIntValue(2026)
    year_field = year.findChild(QSpinBox)
    for field in (window.date_input, window.layer, window.tolerance, window.mail_panel.zone,
                  dialog.category_input, dialog.status_input, dialog.fact_start, dialog.fact_end, year_field):
        before = value(field)
        wheel(field)
        assert value(field) == before
    window.tolerance.setValue(10)
    QTest.keyClick(window.tolerance, Qt.Key.Key_Up)
    assert window.tolerance.value() == 11
    dialog.status_input.setCurrentIndex(0)
    QTest.keyClick(dialog.status_input, Qt.Key.Key_Down)
    assert dialog.status_input.currentIndex() == 1
    QTest.keyClick(year_field, Qt.Key.Key_Up)
    assert year.intValue() == 2027
    year.close()
    dialog.close()
    window.close()
