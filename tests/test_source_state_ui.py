from dataclasses import replace

from PySide6.QtCore import QDate, QEvent
from PySide6.QtWidgets import QApplication

from director_control.storage import Store
from director_control.ui import MainWindow
from tests.test_mail_calendar import event, parse


def test_cancelled_missing_event_has_same_meaning_in_agenda_inspector_and_analytics(tmp_path):
    app = QApplication.instance() or QApplication([])
    store = Store(tmp_path/'db')
    initial = parse(event())
    store.apply_calendar_snapshot(initial)
    original = store.daily_events('2026-10-22')[0]
    store.freeze_day('2026-10-22')
    store.update_event(original.id, status='cancelled')
    assert store.apply_calendar_snapshot(replace(initial, events=()))['missing'] == 0
    window = MainWindow(store)
    window.set_date(QDate(2026, 10, 22))
    window.set_view('agenda')
    window.select_event(original.id)
    assert 'Отменено' in window.table.item(0, 5).text()
    assert 'нет в Mail.ru' in window.table.item(0, 5).text()
    assert 'проверить' not in window.table.item(0, 5).text()
    assert 'нет в Mail.ru' in window.inspector.status.text()
    assert 'проверить' not in window.inspector.status.text()
    assert store.analytics_report('2026-10-22', 'day', only_tracked=False).source_warnings == 0
    window.close()
    window.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
