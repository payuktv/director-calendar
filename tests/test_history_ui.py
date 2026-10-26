"""History browsing with real filters, dialogs, pagination and both themes."""
import json

import pytest
from PySide6.QtCore import QDate, QEvent, QPoint, QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from director_control.history_ui import HistoryEntryDialog
from director_control.storage import Store
from director_control.theme import apply_theme
from director_control.ui import MainWindow
from tests.test_history import event, record


@pytest.fixture
def window(tmp_path):
    app = QApplication.instance() or QApplication([])
    app.setStyle('Fusion')
    w = MainWindow(Store(tmp_path / 'history-ui.db'))
    w.resize(1100, 850)
    w.show()
    w.tabs.setCurrentIndex(2)
    QTest.qWait(20)
    yield w
    w.close()
    w.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    apply_theme('light')


def bulk(store, count=425):
    with store._connect() as con:
        con.executemany('INSERT INTO audit(title,action,details,changed_at) VALUES (?,?,?,?)',
                        [(f'Запись {i:04}', 'Изменение', json.dumps({'status': {'было': 'pending', 'стало': 'done'}}),
                          '2026-10-26T12:00:00') for i in range(count)])


def test_browse_beyond_300_search_old_records_and_change_page_size(window):
    bulk(window.store)
    h = window.history_page
    h.refresh_latest()
    assert h.table.rowCount() == 100 and h.count.text() == '1–100 из 425'
    for _ in range(4):
        QTest.mouseClick(h.older_button, Qt.MouseButton.LeftButton)
    assert h.count.text() == '401–425 из 425' and not h.older_button.isEnabled()
    assert h.rows[-1]['title'] == 'Запись 0000'
    QTest.mouseClick(h.newer_button, Qt.MouseButton.LeftButton)
    assert h.count.text() == '301–400 из 425'
    h.search.setText('ЗАПИСЬ 0000 ВЫПОЛНЕНО')
    QTest.qWait(350)
    assert len(h.rows) == 1 and h.rows[0]['title'] == 'Запись 0000'
    assert h.table.item(0, 3).text() == 'Статус: Не подтверждено → Выполнено'
    QTest.mouseClick(h.reset_button, Qt.MouseButton.LeftButton)
    h.page_size.setCurrentIndex(h.page_size.findData(200))
    assert h.table.rowCount() == 200 and window.store.get_setting('ui_history_page_size') == '200'
    assert window.store.audit_page().total == 425  # Interface choices don't add audit records.


def test_combined_date_event_and_text_filters_and_reset(window):
    store, h = window.store, window.history_page
    eid = event(store, 'Ёж — рабочее совещание')
    store.update_event(eid, title='Итоговое совещание')
    record(store, event_id=eid, title='Итоговое совещание', changed_at='2026-10-20T23:59:59')
    record(store, event_id=eid, title='Итоговое совещание', changed_at='2026-10-21T00:00:00')
    record(store, title='Параметры', changed_at='2026-10-20T12:00:00')
    h.refresh_latest()
    h.event_filter.setEditText('ЕЖ')  # Old name, case and ё/е work for the entire event history.
    h.date_from.setDate(QDate(2026, 10, 20))
    h.date_to.setDate(QDate(2026, 10, 20))
    h.date_enabled.setChecked(True)
    h.search.setText('Выполнено')
    QTest.qWait(350)
    assert len(h.rows) == 1 and h.rows[0]['changed_at'] == '2026-10-20T23:59:59'
    QTest.mouseClick(h.reset_button, Qt.MouseButton.LeftButton)
    assert len(h.rows) == 5 and not h.date_enabled.isChecked()
    h.event_filter.setCurrentIndex(h.event_filter.findData('system'))
    QTest.qWait(350)
    assert len(h.rows) == 1 and h.rows[0]['event_id'] is None


def test_new_records_preserve_older_page_selection_scroll_and_refresh_reaches_latest(window):
    store, h = window.store, window.history_page
    bulk(store)
    h.refresh_latest()
    h.go_older()
    ids = [row['id'] for row in h.rows]
    h.table.setCurrentCell(20, 0)
    h.table.verticalScrollBar().setValue(15)
    scroll = h.table.verticalScrollBar().value()
    newest = record(store, title='Новое изменение')
    window.reload()
    assert h.page_index == 1 and [row['id'] for row in h.rows] == ids
    assert h.rows[h.table.currentRow()]['id'] == ids[20]
    assert h.table.verticalScrollBar().value() == scroll
    assert 'Новых записей' in h.message.text()
    QTest.mouseClick(h.refresh_button, Qt.MouseButton.LeftButton)
    assert h.page_index == 0 and h.rows[0]['id'] == newest
    assert h.page.total == 426


def test_selected_row_filters_deleted_event_and_dialog_keeps_its_history(window):
    store, h = window.store, window.history_page
    eid = event(store, 'Удалённая рабочая встреча')
    store.update_event(eid, status='done')
    store.delete_event(eid)
    event(store, 'Другая встреча')
    h.refresh_latest()
    row = next(i for i, entry in enumerate(h.rows) if entry['event_id'] == eid)
    h.table.setCurrentCell(row, 0)
    QTest.mouseClick(h.selected_event_button, Qt.MouseButton.LeftButton)
    assert len(h.rows) == 3 and all(row['event_id'] == eid for row in h.rows)
    assert 'удалено' in h.event_filter.currentText()
    dialog = HistoryEntryDialog(store, h.rows[0], window)
    assert not dialog.open_button.isEnabled()
    assert 'revision' not in dialog.details.toPlainText() and 'Источник: Локально' in dialog.details.toPlainText()
    dialog.close()


def test_enter_opens_full_plain_text_description_and_event_link(window):
    store, h = window.store, window.history_page
    eid = event(store)
    long_note = '<b>Итог встречи</b>\n' + ('Подробности ' * 180)
    store.update_event(eid, note=long_note, actual_start='2026-10-26T09:10:00', actual_end='2026-10-26T10:30:00')
    h.refresh_latest()
    errors, requested = [], []
    # Test the History link while keeping the already-covered event form out of this modal test.
    h.open_requested.disconnect()
    h.open_requested.connect(requested.append)

    def inspect():
        dialog = QApplication.activeModalWidget()
        try:
            assert isinstance(dialog, HistoryEntryDialog)
            full = dialog.details.toPlainText()
            assert long_note.strip() in full and 'Фактическое начало: не заполнено → 26.10.2026 09:10' in full
            assert 'actual_start' not in full and dialog.details.isReadOnly()
            QTest.mouseClick(dialog.open_button, Qt.MouseButton.LeftButton)
        except BaseException as exc:
            errors.append(exc)
            if dialog:
                dialog.reject()

    QTimer.singleShot(0, inspect)
    h.table.setCurrentCell(0, 0)
    QTest.keyClick(h.table, Qt.Key.Key_Return)
    if errors:
        raise errors[0]
    assert requested == [eid]


def test_invalid_dates_and_read_failure_clear_stale_results_and_recover(window, monkeypatch):
    store, h = window.store, window.history_page
    record(store)
    h.refresh_latest()
    assert h.table.rowCount() == 1
    h.date_from.setDate(QDate(2026, 10, 27))
    h.date_to.setDate(QDate(2026, 10, 26))
    h.date_enabled.setChecked(True)
    assert h.table.rowCount() == 0 and not h.error.isHidden()
    assert 'Дата' in h.error.text() and not h.older_button.isEnabled()
    h.date_from.setDate(QDate(2026, 10, 26))
    assert h.table.rowCount() == 1 and h.error.isHidden()
    original = store.audit_page

    def fail(**kwargs):
        raise OSError('Не удалось прочитать журнал')

    monkeypatch.setattr(store, 'audit_page', fail)
    h.refresh()
    assert not h.rows and h.table.rowCount() == 0 and h.count.text() == 'Записи не показаны'
    monkeypatch.setattr(store, 'audit_page', original)
    h.refresh_latest()
    assert h.table.rowCount() == 1 and h.error.isHidden()


@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_narrow_window_long_event_name_and_shared_date_picker(window, theme):
    store, h = window.store, window.history_page
    eid = event(store, 'Очень длинное название события ' * 6)
    h.refresh_latest()
    h.event_filter.setCurrentIndex(h.event_filter.findData(eid))
    QTest.qWait(350)
    apply_theme(theme)
    window.resize(1000, 700)
    h.date_enabled.setChecked(True)
    QTest.qWait(30)
    assert window.width() == 1000 and h.table.width() < 780
    assert h.event_filter.width() < 700
    QTest.mouseClick(h.date_from, Qt.MouseButton.LeftButton, pos=QPoint(30, h.date_from.height() // 2))
    QApplication.processEvents()
    assert h.date_from._date_picker.popup.isVisible()
    QTest.mouseClick(h.date_from, Qt.MouseButton.LeftButton, pos=QPoint(30, h.date_from.height() // 2))
    QApplication.processEvents()
    assert not h.date_from._date_picker.popup.isVisible()


def test_refresh_applies_pending_search_from_first_page_and_skips_reads_during_restore(window, monkeypatch):
    store, h = window.store, window.history_page
    bulk(store)
    h.refresh_latest()
    h.go_older()
    h.search.setText('Запись 0424')
    assert h.timer.isActive()
    window.reload()
    assert h.page_index == 0 and len(h.rows) == 1 and h.rows[0]['title'] == 'Запись 0424'
    calls = []
    monkeypatch.setattr(store, 'audit_page', lambda **kwargs: calls.append(kwargs))
    # Backup recovery disables the main window until the file replacement finishes.
    window.setEnabled(False)
    h.refresh()
    h.apply_filters()
    window.setEnabled(True)
    assert calls == [] and h.dirty
