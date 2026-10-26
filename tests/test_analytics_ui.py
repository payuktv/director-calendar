"""Dashboard integration: actual widgets, period scope, fact editing and export."""
import csv
from datetime import date

import pytest
from PySide6.QtCore import QDate, QEvent, QPoint, QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog

from director_control.local_event_dialog import LocalEventDialog
from director_control.storage import Store
from director_control.theme import apply_theme, color
from director_control.ui import MainWindow, qt_datetime

DAY = '2026-10-19'


@pytest.fixture
def window(tmp_path):
    app = QApplication.instance() or QApplication([])
    app.setStyle('Fusion')
    store = Store(tmp_path / 'analytics-ui.db')
    w = MainWindow(store)
    w.set_date(QDate(2026, 10, 19))
    w.resize(1100, 850)
    w.show()
    w.tabs.setCurrentIndex(1)
    app.processEvents()
    yield w
    w.close()
    w.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    apply_theme('light')


def event(window, **kwargs):
    return window.store.create_event('Рабочая встреча', 'Работа', DAY+'T09:00:00', DAY+'T10:00:00', **kwargs)


def test_period_switch_and_independence_from_calendar_search_and_layers(window):
    a, store = window.analytics_page, window.store
    event(window, status='done')
    store.freeze_day(DAY)
    window.reload()
    assert a.report.start == date(2026, 10, 19) and a.report.end == date(2026, 10, 26)
    QTest.mouseClick(a.mode_buttons['month'], Qt.MouseButton.LeftButton)
    assert a.report.start == date(2026, 10, 1) and a.report.end == date(2026, 11, 1)
    assert store.get_setting('ui_analytics_mode') == 'month'
    window.search.setText('несуществующая запись')
    window.layer.setCurrentIndex(window.layer.findData('actual'))
    assert a.report.totals.planned == 1
    a.set_anchor(date(2027, 1, 1))
    QTest.mouseClick(a.mode_buttons['week'], Qt.MouseButton.LeftButton)
    assert a.report.start == date(2026, 12, 28) and a.report.end == date(2027, 1, 4)
    assert window.selected_sync_day() == '2027-01-01'
    assert window.selected_day() == DAY
    window.tabs.setCurrentIndex(0)
    assert window.selected_sync_day() == DAY
    window.set_date(QDate(2026, 10, 21))
    window.tabs.setCurrentIndex(1)
    assert a.anchor == date(2026, 10, 21)


def test_missing_card_opens_real_editor_and_saved_fact_updates_analytics(window):
    a = window.analytics_page
    eid = event(window, status='done')
    window.store.freeze_day(DAY)
    window.reload()
    assert a.cards['missing'].value.text() == '1'
    QTest.mouseClick(a.cards['missing'], Qt.MouseButton.LeftButton)
    assert a.details.currentIndex() == 3
    assert [r.event.id for r in a.event_rows] == [eid]
    errors = []

    def fill():
        dialog = QApplication.activeModalWidget()
        try:
            assert isinstance(dialog, LocalEventDialog)
            dialog.fact_checkbox.setChecked(True)
            dialog.fact_start.setDateTime(qt_datetime(DAY+'T09:20:00'))
            dialog.fact_end.setDateTime(qt_datetime(DAY+'T10:30:00'))
            dialog.save()
        except BaseException as exc:
            errors.append(exc)
            if dialog:
                dialog.reject()

    QTimer.singleShot(0, fill)
    a.event_table.setCurrentCell(0, 0)
    QTest.keyClick(a.event_table, Qt.Key.Key_Return)
    if errors:
        raise errors[0]
    assert window.store.get_event(eid).actual_start == DAY+'T09:20:00'
    assert a.cards['missing'].value.text() == '0'
    assert a.report.totals.actual_seconds == 70 * 60 and a.report.totals.mean_start_minutes == 20
    assert a.anchor == date(2026, 10, 19)


def test_lower_bound_unknown_filter_and_day_drill(window):
    a = window.analytics_page
    eid = event(window, status='done', actual_start=DAY+'T09:00:00', actual_end=DAY+'T10:00:00')
    window.store.create_event('Срочное', 'Работа', actual_start=DAY+'T10:00:00', actual_end=DAY+'T11:00:00')
    window.reload()
    assert a.cards['unplanned'].value.text() == '≥ 50%'
    assert 'неизвестно' in a.quality.text()
    a.show_events('unfixed')
    assert [r.event.id for r in a.event_rows] == [eid]
    a.show_day(date(2026, 10, 20))
    assert a.event_table.rowCount() == 0 and not a.reset_day.isHidden()
    QTest.mouseClick(a.reset_day, Qt.MouseButton.LeftButton)
    assert a.event_table.rowCount() == 2
    assert a.report.totals.actual_seconds == 2 * 3600


@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_theme_empty_states_single_click_picker_and_narrow_layout(window, theme):
    apply_theme(theme)
    window.resize(1000, 700)
    app, a = QApplication.instance(), window.analytics_page
    app.processEvents()
    assert window.width() == 1000
    assert a.cards['completion'].value.text() == a.cards['unplanned'].value.text() == '—'
    assert a.cards['start'].value.text() == a.cards['duration'].value.text() == '—'
    QTest.mouseClick(a.date_input, Qt.MouseButton.LeftButton, pos=QPoint(35, a.date_input.height() // 2))
    app.processEvents()
    popup = a.date_input._date_picker.popup
    assert popup.isVisible()
    QTest.mouseClick(a.date_input, Qt.MouseButton.LeftButton, pos=QPoint(35, a.date_input.height() // 2))
    app.processEvents()
    assert not popup.isVisible()
    for card in a.cards.values():
        assert card.value.width() > 100
    a.show_events()
    app.processEvents()
    assert window.width() == 1000 and a.event_table.width() < 760


def test_csv_exports_whole_period_scope_even_when_details_filtered(window, tmp_path, monkeypatch):
    event(window, status='done')
    window.store.freeze_day(DAY)
    a = window.analytics_page
    a.set_mode('month')
    a.only_tracked.setChecked(False)
    a.show_events('unplanned')
    assert a.event_table.rowCount() == 0
    path = tmp_path / 'month.csv'
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *args, **kwargs: (str(path), 'CSV'))
    QTest.mouseClick(a.export_button, Qt.MouseButton.LeftButton)
    with path.open(encoding='utf-8-sig') as stream:
        rows = list(csv.DictReader(stream, delimiter=';'))
    assert len(rows) == 32 and rows[0]['В плане'] == '1' and rows[0]['Категории'] == 'Все'
    assert rows[0]['С'] == '2026-10-01' and rows[0]['По'] == '2026-10-31'
    assert rows[1]['Исполнение, %'] == ''
    assert window.store.get_setting('ui_analytics_only_tracked') == '0'


def test_report_failure_clears_stale_charts_rows_and_export(window, monkeypatch):
    event(window, status='done', actual_start=DAY+'T09:00:00', actual_end=DAY+'T10:00:00')
    window.reload()
    a = window.analytics_page
    assert a.category_bars.values and a.event_rows and a.daily_bars.report
    a.show_day(date(2026, 10, 19))

    def fail(*args):
        raise OSError('Тестовая ошибка чтения')

    monkeypatch.setattr(window.store, 'analytics_report', fail)
    a.refresh()
    assert a.report is None and not a.export_button.isEnabled()
    assert not a.category_bars.values and not a.event_rows and a.daily_bars.report is None
    assert a.day_table.rowCount() == a.category_table.rowCount() == a.event_table.rowCount() == 0
    assert a.cards['actual'].value.text() == '—' and 'Тестовая ошибка' in a.quality.text()
    assert a.reset_day.isHidden() and a.events_note.text() == 'Отчёт недоступен'


def test_calendar_and_report_use_start_and_duration_with_strict_frozen_tolerance(window):
    eid = event(window, status='done', actual_start=DAY+'T09:10:00', actual_end=DAY+'T10:20:00')
    window.store.freeze_day(DAY)
    window.store.set_setting('tolerance_minutes', '60')
    window.reload()
    a = window.analytics_page
    row = a.report.events[0]
    assert row.start_delta == row.duration_delta == 10 and not row.outside_tolerance
    assert a.report.totals.start_outside == a.report.totals.duration_outside == 0
    window.set_view('agenda')
    assert 'отклонение' not in window.table.item(0, 5).text()
    window.store.update_event(eid, actual_end=DAY+'T10:21:00')
    window.reload()
    assert a.report.totals.start_outside == 0 and a.report.totals.duration_outside == 1
    assert 'отклонение' in window.table.item(0, 5).text()
    assert a.event_table.item(0, 5).foreground().style() == Qt.BrushStyle.NoBrush
    assert a.event_table.item(0, 6).foreground().color() == color('danger')
