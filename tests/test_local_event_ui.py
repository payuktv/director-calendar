"""The local event form and its calendar, menu and inspector integration."""
import gc
from datetime import datetime

import pytest
from PySide6.QtCore import QDate, QEvent, QPoint, QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
from shiboken6 import isValid

from director_control.calendar_view import event_interval
from director_control.date_picker import MiniCalendar
from director_control.input_wheel import install_input_wheel_guard
from director_control.local_event_dialog import LocalEventDialog
from director_control.storage import Store
from director_control.theme import apply_theme
from director_control.ui import MainWindow, qt_datetime
from tests.test_context_menu import choose_menu_action

DAY = '2026-10-22'
START = datetime(2026, 10, 22, 11)


@pytest.fixture
def app():
    gc.collect()
    app = QApplication.instance() or QApplication([])
    app.setStyle('Fusion')
    install_input_wheel_guard(app)
    apply_theme('light')
    yield app
    apply_theme('light')


@pytest.fixture
def keep(app):
    objects = []
    def register(obj):
        objects.append(obj)
        return obj
    yield register
    for obj in reversed(objects):
        if isValid(obj):
            obj.close()
            obj.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / 'local-ui.db')


def finish_modal(app, invoke, action):
    errors = []
    def fill():
        dialog = app.activeModalWidget()
        try:
            assert isinstance(dialog, LocalEventDialog)
            action(dialog)
        except BaseException as exc:
            errors.append(exc)
            if dialog:
                dialog.reject()
    QTimer.singleShot(0, fill)
    invoke()
    if errors:
        raise errors[0]
    app.processEvents()


def test_postfactum_form_defaults_validation_and_single_save(app, keep, store):
    dialog = keep(LocalEventDialog(store, START))
    assert dialog.kind_input.currentData() == 'actual'
    assert dialog.status_input.currentData() == 'done'
    assert not dialog.form.isRowVisible(dialog.fact_checkbox)
    assert not dialog.save_button.isEnabled()
    dialog.title_input.setText('Срочный разговор')
    dialog.note_input.setPlainText('Подробности\nИтоги')
    dialog.end_input.setDateTime(dialog.start_input.dateTime())
    dialog.save()
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert 'позже начала' in dialog.error_label.text()
    assert store.daily_events(DAY) == []
    dialog.end_input.setDateTime(dialog.start_input.dateTime().addSecs(1800))
    dialog.save()
    dialog.save()  # A repeated submit cannot create a duplicate.
    event = store.get_event(dialog.event_id)
    assert event.is_postfactum and event.status == 'done'
    assert event.actual_start == DAY+'T11:00:00' and event.current_start is None
    assert event.note == 'Подробности\nИтоги'
    assert len(store.daily_events(DAY)) == 1 and len(store.audit_log()) == 1


def test_local_plan_form_keeps_fact_optional_and_reject_does_not_create(app, keep, store):
    rejected = keep(LocalEventDialog(store, START))
    rejected.title_input.setText('Не сохранять')
    rejected.reject()
    assert store.audit_log() == []
    dialog = keep(LocalEventDialog(store, START))
    dialog.title_input.setText('Подготовить отчёт')
    dialog.kind_input.setCurrentIndex(dialog.kind_input.findData('planned'))
    assert dialog.status_input.currentData() == 'pending'
    assert dialog.form.isRowVisible(dialog.fact_checkbox) and not dialog.fact_checkbox.isChecked()
    dialog.save()
    event = store.get_event(dialog.event_id)
    assert event.current_start == DAY+'T11:00:00'
    assert event.actual_start is None and event.baseline_start is None


@pytest.mark.parametrize('mode', ['day', 'week', 'month', 'agenda'])
def test_add_button_shows_postfactum_in_every_view_without_sync(app, keep, store, monkeypatch, mode):
    window = keep(MainWindow(store))
    window.resize(1450, 930)
    window.set_date(QDate(2026, 10, 22))
    window.set_view(mode)
    window.show()
    app.processEvents()
    syncs = []
    monkeypatch.setattr(window.mail_panel, 'sync', lambda: syncs.append(True))
    window.layer.setCurrentIndex(window.layer.findData('baseline'))
    window.search.setText('несовпадающий поиск')
    def fill(dialog):
        dialog.title_input.setText('Внеплановый разговор')
        dialog.start_input.setDateTime(qt_datetime(DAY+'T11:00:00'))
        dialog.end_input.setDateTime(qt_datetime(DAY+'T11:30:00'))
        dialog.save()
    finish_modal(app, window.add_event_button.click, fill)
    event = store.daily_events(DAY)[0]
    assert not syncs and event.source == 'local' and event.is_postfactum
    assert window.selected_event_id() == event.id and window.search.text() == ''
    assert window.layer.currentData() == 'current'
    assert window.inspector.category.text().endswith('Локально')
    assert window.inspector.time_labels['current'].text() == 'Не планировалось'
    assert window.cards['unplanned'].value.text() == '1' and window.cards['planned'].value.text() == '0'
    if mode == 'agenda':
        assert window.row_ids == [event.id] and 'Локально' in window.table.item(0, 6).text()
    else:
        canvas = window.calendar.month if mode == 'month' else window.calendar.grid
        assert any(item.id == event.id for _, item in canvas.hits)
    assert event_interval(event, 'baseline') is None
    assert event_interval(event, 'current') == event_interval(event, 'actual')


def test_local_event_can_be_opened_edited_and_its_status_changed(app, keep, store):
    eid = store.create_event('Разговор', 'Работа', actual_start=DAY+'T11:00:00', actual_end=DAY+'T11:30:00')
    window = keep(MainWindow(store))
    window.set_date(QDate(2026, 10, 22))
    window.set_view('day')
    window.show()
    app.processEvents()
    def edit(dialog):
        assert not dialog.kind_input.isEnabled() and dialog.title_input.isEnabled()
        dialog.title_input.setText('Уточнённый разговор')
        dialog.start_input.setDateTime(qt_datetime('2026-10-23T12:00:00'))
        dialog.end_input.setDateTime(qt_datetime('2026-10-23T12:30:00'))
        dialog.save()
    finish_modal(app, lambda: window.open_event(eid), edit)
    assert window.selected_day() == '2026-10-23'
    assert store.get_event(eid).title == 'Уточнённый разговор'
    choose_menu_action(app, lambda: window.show_event_context_menu(eid, window.mapToGlobal(QPoint(350, 250))), 'partial')
    event = store.get_event(eid)
    assert event.status == 'partial' and event.current_start is event.baseline_start is None
    assert window.inspector.status.text() == 'Вне плана · Частично'


def test_delete_is_confirmed_audited_and_disabled_for_frozen_plan(app, keep, store, monkeypatch):
    eid = store.create_event('Ошибка ввода', 'Работа', actual_start=DAY+'T11:00:00', actual_end=DAY+'T11:30:00')
    event = store.get_event(eid)
    dialog = keep(LocalEventDialog(store, START, event))
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.No)
    dialog.delete_button.click()
    assert store.get_event(eid) == event
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Yes)
    dialog.delete_button.click()
    assert dialog.event_id is None and dialog.result() == QDialog.DialogCode.Accepted
    assert store.audit_log()[0]['action'] == 'Удаление локального события'
    planned = store.create_event('План', 'Работа', DAY+'T09:00:00', DAY+'T10:00:00')
    store.freeze_day(DAY)
    frozen = keep(LocalEventDialog(store, START, store.get_event(planned)))
    assert not frozen.delete_button.isEnabled()
    frozen.title_input.setText('Изменённый план')
    frozen.start_input.setDateTime(qt_datetime(DAY+'T10:30:00'))
    frozen.end_input.setDateTime(qt_datetime(DAY+'T11:30:00'))
    frozen.save()
    assert store.get_event(planned).baseline_start == DAY+'T09:00:00'


@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_shared_date_picker_works_in_local_form_and_theme_is_readable(app, keep, store, theme):
    apply_theme(theme)
    dialog = keep(LocalEventDialog(store, START))
    dialog.show()
    app.processEvents()
    assert isinstance(dialog.start_input.calendarWidget(), MiniCalendar)
    QTest.mouseClick(dialog.start_input.lineEdit(), Qt.MouseButton.LeftButton, pos=QPoint(8, 10))
    app.processEvents()
    assert dialog.start_input._date_picker.popup.isVisible()
    QTest.mouseClick(dialog.start_input.lineEdit(), Qt.MouseButton.LeftButton, pos=QPoint(8, 10))
    app.processEvents()
    assert not dialog.start_input._date_picker.popup.isVisible()
    palette = dialog.note_input.palette()
    assert (palette.color(palette.ColorRole.Base).lightness() < 80) == (theme == 'dark')


def test_local_events_also_prevent_timezone_reinterpretation(app, keep, store):
    eid = store.create_event('Факт', 'Работа', actual_start=DAY+'T11:00:00', actual_end=DAY+'T11:30:00')
    before = store.get_event(eid)
    window = keep(MainWindow(store))
    panel = window.mail_panel
    panel.url.setText('https://calendar.mail.ru/principals/test/calendars/example/')
    panel.login.setText('test@example.test')
    panel.zone.setCurrentText('UTC')
    panel.save_connection()
    assert 'часовой пояс менять нельзя' in panel.status.text()
    assert store.get_event(eid) == before and store.get_setting('mail_timezone', 'Europe/Moscow') == 'Europe/Moscow'


def test_selection_of_a_local_record_deleted_in_another_window_refreshes_safely(app, keep, store):
    eid = store.create_event('Факт', 'Работа', actual_start=DAY+'T11:00:00', actual_end=DAY+'T11:30:00')
    window = keep(MainWindow(store))
    window.set_date(QDate(2026, 10, 22))
    store.delete_event(eid)
    window.select_event(eid)
    window.open_event(eid)
    assert window.selected_event_id() is None and window.row_ids == []


def test_new_late_event_is_revealed_in_the_time_grid(app, keep, store):
    window = keep(MainWindow(store))
    window.resize(1150, 760)
    window.set_view('day')
    window.show()
    app.processEvents()
    def fill(dialog):
        dialog.title_input.setText('Поздний звонок')
        dialog.start_input.setDateTime(qt_datetime(DAY+'T23:00:00'))
        dialog.end_input.setDateTime(qt_datetime(DAY+'T23:30:00'))
        dialog.save()
    finish_modal(app, window.add_event_button.click, fill)
    app.processEvents()
    y = 23 * window.calendar.hour_height
    bar = window.calendar.scroll.verticalScrollBar()
    assert bar.value() <= y < bar.value() + window.calendar.scroll.viewport().height()
