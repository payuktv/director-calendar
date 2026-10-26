import json

from director_control.storage import Store

DAY = '2026-10-26'


def test_baseline_percent_category_and_tolerance_survive_setting_changes(tmp_path):
    store = Store(tmp_path / 'rules.db')
    first = store.create_event('Встреча', 'Встречи', DAY+'T09:00:00', DAY+'T10:00:00', status='done')
    second = store.create_event('Подготовка', 'Работа', DAY+'T10:00:00', DAY+'T11:00:00')
    store.freeze_day(DAY)
    assert store.day_summary(DAY)['percent'] == 50
    store.set_category_tracking('Работа', False)
    store.set_setting('tolerance_minutes', '60')
    store.update_event(second, category='Отдых')
    restarted = Store(store.path)
    assert restarted.day_summary(DAY)['percent'] == 50
    assert restarted.day_summary(DAY)['planned'] == 2
    assert ('Работа', 60, 0) in restarted.category_totals(DAY)
    rules = restarted.baseline_rules()
    assert rules[second]['category'] == 'Работа' and rules[second]['track'] == 1
    assert rules[first]['tolerance_minutes'] == 10
    actions = {row['action']: json.loads(row['details']) for row in restarted.audit_log()}
    assert actions['Контроль категории'] == {'было': True, 'стало': False}
    assert actions['Настройка контроля времени'] == {'было': '10', 'стало': '60'}
    store.set_category_tracking('Работа', False)
    assert len([r for r in store.audit_log() if r['action'] == 'Контроль категории']) == 1


def test_deviation_label_uses_frozen_tolerance_not_current_setting(tmp_path):
    from PySide6.QtCore import QDate
    from PySide6.QtWidgets import QApplication
    from director_control.ui import MainWindow
    app = QApplication.instance() or QApplication([])
    store = Store(tmp_path / 'deviation.db')
    store.create_event('Встреча', 'Работа', DAY+'T09:00:00', DAY+'T10:00:00',
                       actual_start=DAY+'T09:00:00', actual_end=DAY+'T10:20:00', status='done')
    store.freeze_day(DAY)
    window = MainWindow(store)
    window.set_date(QDate(2026, 10, 26))
    window.set_view('agenda')
    assert 'отклонение' in window.table.item(0, 5).text()
    store.set_setting('tolerance_minutes', '60')
    window.reload()
    assert 'отклонение' in window.table.item(0, 5).text()
    window.close()
    app.processEvents()
