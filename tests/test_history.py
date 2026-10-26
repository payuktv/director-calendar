"""Full-journal retrieval and readable descriptions, without modifying audit data."""
import json
from datetime import date

import pytest

from director_control.history import describe
from director_control.storage import Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / 'history.db')


def record(store, *, title='Совещание', action='Изменение', details=None,
           changed_at='2026-10-26T12:00:00', event_id=None):
    with store._connect() as con:
        return con.execute('INSERT INTO audit(event_id,title,action,details,changed_at) VALUES (?,?,?,?,?)',
                           (event_id, title, action, json.dumps(details or {'status': {'было': 'pending', 'стало': 'done'}}, ensure_ascii=False), changed_at)).lastrowid


def event(store, title='Название до изменения'):
    return store.create_event(title, 'Работа', '2026-10-26T09:00:00', '2026-10-26T10:00:00')


@pytest.mark.parametrize('action,data,expected,hidden', [
    ('Изменение', {'status': {'было': 'pending', 'стало': 'done'}}, 'Статус: Не подтверждено → Выполнено', 'pending'),
    ('Изменение', {'actual_start': {'было': None, 'стало': '2026-10-26T09:15:30'}}, 'Фактическое начало: не заполнено → 26.10.2026 09:15:30', 'actual_start'),
    ('Импорт Mail.ru', {'start': '2026-10-26T09:00:00', 'end': '2026-10-26T10:00:00'}, 'Начало расписания: 26.10.2026 09:00', '"start"'),
    ('Фиксация плана', {'day': '2026-10-26'}, 'Дата плана: 26.10.2026', '"day"'),
    ('Настройка контроля времени', {'было': '10', 'стало': '20'}, 'Допустимое отклонение: 10 мин → 20 мин', '{'),
    ('Контроль категории', {'было': True, 'стало': False}, 'Участие категории в контроле: включено → выключено', 'false'),
    ('Настройки копирования', {'backup_auto': {'было': '1', 'стало': '0'}, 'backup_folder': {'было': '', 'стало': 'D:/Копии'}}, 'Ежедневные резервные копии: включено → выключено', 'backup_auto'),
    ('Обновление Mail.ru', {'источник': {'missing': False, 'cancelled': True, 'all_day': False}}, 'Отменено в Mail.ru: да', 'missing'),
    ('Удаление локального события', {'id': 17, 'revision': 4, 'title': 'Отмена', 'source': 'local'}, 'Источник: Локально в приложении', 'revision'),
])
def test_readable_known_actions_fields_and_values(action, data, expected, hidden):
    rendered = describe(action, json.dumps(data, ensure_ascii=False))
    assert expected in rendered.details and hidden not in rendered.details
    assert rendered.action


@pytest.mark.parametrize('raw', ['старое описание без JSON', '{invalid', '["первое", "второе"]', 'null'])
def test_legacy_and_malformed_payload_does_not_break_history(raw):
    rendered = describe('Давняя запись', raw)
    assert rendered.details and rendered.action == 'Давняя запись'


def test_source_absence_is_not_reported_as_confirmed_deletion():
    rendered = describe('Нет в ответе Mail.ru', '{"требует проверки": true}')
    assert 'провер' in rendered.details.lower() and 'не подтверждает удаление' in rendered.details


def test_cursor_pages_reach_every_old_record_and_are_stable_when_new_entries_arrive(store):
    with store._connect() as con:
        con.executemany('INSERT INTO audit(event_id,title,action,details,changed_at) VALUES (NULL,?,?,?,?)',
                        [(f'Запись {i}', 'Изменение', '{}', '2026-10-26T12:00:00') for i in range(750)])
    first = store.audit_page(limit=100)
    assert first.total == 750 and len(first.rows) == 100
    # The original short API stays compatible; the paged API has no 300-record cap.
    assert len(store.audit_log()) == 300
    seen = [r['id'] for r in first.rows]
    new_id = record(store, title='Новая запись')
    page = first
    while page.has_older:
        page = store.audit_page(limit=100, before_id=page.rows[-1]['id'], ceiling_id=first.ceiling_id)
        seen.extend(r['id'] for r in page.rows)
        assert page.total == 750 and page.newer_count == 1
    assert len(seen) == len(set(seen)) == 750
    assert seen == list(range(750, 0, -1)) and new_id not in seen
    newest = store.audit_page()
    assert newest.total == 751 and newest.rows[0]['id'] == new_id


def test_unicode_search_uses_readable_statuses_all_terms_and_literal_characters(store):
    record(store, title='Ёлка — итоговое совещание', details={'status': {'было': 'partial', 'стало': 'done'}, 'note': {'было': '', 'стало': 'Бюджет 15%_2026'}})
    record(store, title='Другая встреча', details={'note': {'было': '', 'стало': 'Бюджет 15002026'}})
    assert store.audit_page(search='ЕЛКА ВЫПОЛНЕНО').total == 1
    assert store.audit_page(search='ЧАСТИЧНО').total == 1
    assert store.audit_page(search='15%_2026').total == 1
    assert store.audit_page(search="' OR 1=1 --").total == 0
    assert store.audit_page(search='Фактическое начало').total == 0


def test_inclusive_change_dates_and_combined_filters(store):
    eid = event(store)
    with store._connect() as con:
        con.execute('DELETE FROM audit')
    for stamp in ('2028-02-28T23:59:59', '2028-02-29T00:00:00', '2028-02-29T23:59:59', '2028-03-01T00:00:00'):
        record(store, event_id=eid, changed_at=stamp)
    record(store, title='Настройки', changed_at='2028-02-29T12:00:00')
    page = store.audit_page(date_from=date(2028, 2, 29), date_to='2028-02-29', event_id=eid, search='Выполнено')
    assert page.total == 2
    assert store.audit_page(date_to='2028-02-29').total == 4
    assert store.audit_page(date_from='2028-03-01').total == 1
    assert store.audit_page(event_id='system', date_from='2028-02-29', date_to='2028-02-29').total == 1
    with pytest.raises(ValueError, match='Дата'):
        store.audit_page(date_from='2028-03-01', date_to='2028-02-29')


def test_event_filter_includes_renames_deleted_records_and_distinguishes_identical_titles(store):
    eid = event(store)
    store.update_event(eid, title='Новое название')
    duplicate = event(store, 'Новое название')
    before_delete = store.audit_page(event_id=eid)
    assert before_delete.total == 2
    store.delete_event(eid)
    options = {r['event_id']: r for r in store.audit_event_options()}
    assert options[eid]['deleted'] and options[eid]['title'] == 'Новое название'
    assert not options[duplicate]['deleted']
    assert store.audit_page(event_id=eid).total == 3
    assert store.audit_page(event_search='НАЗВАНИЕ ДО').total == 3
    assert store.audit_page(event_search='НОВОЕ НАЗВАНИЕ').total == 4


def test_search_reaches_old_entries_and_reading_preserves_raw_journal(store):
    target = record(store, title='Самая старая запись', details={'actual_start': {'было': None, 'стало': '2026-10-26T11:00:00'}})
    with store._connect() as con:
        con.executemany('INSERT INTO audit(title,action,details,changed_at) VALUES (?,?,?,?)',
                        [('Поздняя запись', 'Изменение', '{}', '2026-10-26T12:00:00')] * 420)
    before = store.path.read_bytes()
    rows = store.audit_page(search='СТАРАЯ ФАКТИЧЕСКОЕ НАЧАЛО').rows
    assert len(rows) == 1 and rows[0]['id'] == target
    assert 'actual_start' in rows[0]['details']  # Stored data remains unchanged.
    store.audit_event_options()
    assert store.path.read_bytes() == before


@pytest.mark.parametrize('kwargs', [{'limit': 0}, {'limit': 501}, {'event_id': 'bad'}, {'before_id': -1}])
def test_invalid_query_boundaries_are_rejected(store, kwargs):
    with pytest.raises(ValueError):
        store.audit_page(**kwargs)
