"""Local plans/facts, accounting, sync isolation and safe v2 database migration."""
import csv
from dataclasses import replace
import json
import sqlite3

import pytest

from director_control.storage import Store
from tests.test_mail_only import imported_snapshot

DAY = '2026-10-22'
START, END = DAY + 'T11:00:00', DAY + 'T11:45:00'


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / 'events.db')


def fact(store, **changes):
    data = dict(title='Срочная встреча', category='Работа', actual_start=START, actual_end=END,
                note='Возникло неожиданно\nИтог обсуждения')
    data.update(changes)
    return store.create_event(**data)


def test_postfactum_never_creates_a_plan_or_improves_its_execution_rate(store, tmp_path):
    store.apply_calendar_snapshot(imported_snapshot())
    remote = store.daily_events(DAY)[0]
    local = fact(store)
    event = store.get_event(local)
    assert event.source == 'local' and event.is_postfactum and event.status == 'done'
    assert event.current_start is event.current_end is event.baseline_start is event.baseline_end is None
    assert (event.actual_start, event.actual_end) == (START, END)
    assert local not in store.calendar_info()
    assert store.freeze_day(DAY) == 1
    assert store.get_event(local) == event
    summary = store.day_summary(DAY)
    assert (summary['planned'], summary['done'], summary['unplanned'], summary['percent']) == (1, 0, 1, 0)
    assert {event.id for event in store.daily_events(DAY)} == {local, remote.id}
    assert ('Работа', 0, 45) in store.category_totals(DAY)
    assert store.coverage_for_day(DAY) == {'gaps': [('07:00', '09:00'), ('10:00', '19:00')], 'overlaps': 0}
    path = tmp_path / 'report.csv'
    store.export_csv(DAY, path)
    with path.open(encoding='utf-8-sig', newline='') as report:
        row = next(r for r in csv.DictReader(report, delimiter=';') if r['ID'] == str(local))
    assert row['Первоначально с'] == row['Актуально с'] == ''
    assert row['Факт с'] == START and row['Источник'] == 'Локально'
    assert 'Итог обсуждения' in row['Комментарий']


def test_local_planned_events_freeze_without_inventing_fact_and_preserve_baseline(store):
    eid = store.create_event('Подготовка', 'Работа', START, END)
    assert store.get_event(eid).status == 'pending'
    assert store.get_event(eid).actual_start is None
    assert store.freeze_day(DAY) == 1
    store.update_event(eid, title='Подготовка материалов', current_start=DAY+'T13:00:00', current_end=DAY+'T14:00:00', status='done')
    event = store.get_event(eid)
    assert event.baseline_start == START and event.baseline_end == END
    assert event.current_start == DAY+'T13:00:00' and event.actual_start is None
    assert store.category_totals(DAY) == [('Работа', 45, 0)]
    with pytest.raises(ValueError, match='зафиксированный план'):
        store.delete_event(eid)
    with pytest.raises(ValueError, match='Недопустимые'):
        store.update_event(eid, baseline_start=None)
    assert store.day_summary(DAY)['planned'] == 1


def test_events_added_after_freeze_stay_unplanned(store):
    store.freeze_day(DAY)
    one = fact(store)
    two = store.create_event('Новое дело', 'Работа', START, END)
    assert store.get_event(one).baseline_start is store.get_event(two).baseline_start is None
    assert store.day_summary(DAY)['unplanned'] == 2
    with pytest.raises(ValueError, match='уже зафиксирован'):
        store.freeze_day(DAY)


def test_sync_and_missing_remote_records_do_not_change_local_records(store):
    local = fact(store)
    before = store.get_event(local)
    snapshot = imported_snapshot()
    store.apply_calendar_snapshot(snapshot)
    assert store.apply_calendar_snapshot(snapshot)['added'] == 0
    store.apply_calendar_snapshot(replace(snapshot, events=()))
    store.apply_calendar_snapshot(replace(snapshot, events=(), unavailable=('temporary',)))
    assert store.get_event(local) == before
    assert len(store.calendar_info()) == 1 and local not in store.calendar_info()
    assert Store(store.path).get_event(local) == before
    actions = [r['action'] for r in store.audit_log() if r['event_id'] == local]
    assert actions == ['Создание локального события']


def test_local_edits_delete_and_history_do_not_touch_mail(store):
    store.apply_calendar_snapshot(imported_snapshot())
    remote = store.daily_events(DAY)[0]
    eid = fact(store)
    store.update_event(eid, title='Итоги встречи', category='Встречи', actual_end=DAY+'T12:00:00', status='partial', note='Новый итог')
    saved = store.get_event(eid)
    assert saved.current_start is None and saved.actual_end == DAY+'T12:00:00'
    assert saved.status == 'partial' and saved.title == 'Итоги встречи'
    with pytest.raises(ValueError, match='Тип существующего'):
        store.update_event(eid, current_start=START, current_end=END)
    with pytest.raises(ValueError, match='время'):
        store.update_event(eid, actual_start=None, actual_end=None)
    for changes in ({'source': 'caldav'}, {'external_key': 'some-key'}, {'baseline_end': END}):
        with pytest.raises(ValueError):
            store.update_event(eid, **changes)
    with pytest.raises(ValueError, match='Mail.ru'):
        store.delete_event(remote.id)
    store.delete_event(eid)
    with pytest.raises(KeyError):
        store.get_event(eid)
    assert store.get_event(remote.id) == remote
    history = [r for r in store.audit_log() if r['event_id'] == eid]
    assert [r['action'] for r in history] == ['Удаление локального события', 'Изменение', 'Создание локального события']
    assert json.loads(history[0]['details'])['note'] == 'Новый итог'
    assert fact(store) > eid


def test_cross_midnight_fact_is_visible_and_clipped_to_each_day(store):
    eid = fact(store, actual_start=DAY+'T23:30:00', actual_end='2026-10-23T00:30:00')
    for day in (DAY, '2026-10-23'):
        assert [event.id for event in store.daily_events(day)] == [eid]
        assert store.day_summary(day)['unplanned'] == 1
        assert store.category_totals(day) == [('Работа', 0, 30)]
        assert store.day_summary(day)['planned'] == 0
    assert store.daily_events('2026-10-24') == []


def test_actual_date_of_mail_event_is_included_in_daily_export_and_totals(store, tmp_path):
    store.apply_calendar_snapshot(imported_snapshot())
    event = store.daily_events(DAY)[0]
    store.update_event(event.id, actual_start='2026-10-23T10:00:00', actual_end='2026-10-23T11:00:00', status='done')
    assert store.daily_events('2026-10-23')[0].id == event.id
    assert store.category_totals('2026-10-23') == [('Mail.ru', 0, 60)]


@pytest.mark.parametrize('changes', [
    {'title': ''}, {'title': '   '}, {'title': None}, {'title': 'x'*201},
    {'category': 'missing'}, {'status': 'missing'},
    {'actual_end': None}, {'actual_start': 'invalid'}, {'actual_end': START},
    {'actual_end': DAY+'T10:00:00'}, {'actual_start': START+'+03:00'},
    {'current_start': START}, {'actual_start': None, 'actual_end': None},
])
def test_invalid_creation_is_atomic(store, changes):
    with pytest.raises(ValueError):
        fact(store, **changes)
    assert store.daily_events(DAY) == [] and store.audit_log() == []


def test_local_times_are_normalized_to_searchable_iso_strings(store):
    eid = fact(store, actual_start=DAY+' 11:00', actual_end=DAY+' 11:30')
    assert store.get_event(eid).actual_start == START
    assert store.daily_events(DAY)[0].id == eid


V2_SCHEMA = '''
CREATE TABLE categories(name TEXT PRIMARY KEY, color TEXT NOT NULL, track INTEGER NOT NULL DEFAULT 1);
CREATE TABLE events(
 id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, category TEXT NOT NULL REFERENCES categories(name),
 current_start TEXT NOT NULL, current_end TEXT NOT NULL, baseline_start TEXT, baseline_end TEXT,
 actual_start TEXT, actual_end TEXT, status TEXT NOT NULL DEFAULT 'pending', note TEXT NOT NULL DEFAULT '',
 source TEXT NOT NULL DEFAULT 'manual', external_key TEXT UNIQUE, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX custom_status_index ON events(status);
CREATE TABLE calendar_events(event_id INTEGER PRIMARY KEY REFERENCES events(id) ON DELETE CASCADE,
 calendar_key TEXT NOT NULL, uid TEXT NOT NULL, recurrence_id TEXT NOT NULL, missing INTEGER NOT NULL DEFAULT 0,
 cancelled INTEGER NOT NULL DEFAULT 0, all_day INTEGER NOT NULL DEFAULT 0, baseline_all_day INTEGER, local_status INTEGER NOT NULL DEFAULT 0);
CREATE TABLE audit(id INTEGER PRIMARY KEY AUTOINCREMENT,event_id INTEGER,title TEXT NOT NULL,action TEXT NOT NULL,details TEXT NOT NULL,changed_at TEXT NOT NULL);
CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE day_freezes(day TEXT PRIMARY KEY,frozen_at TEXT NOT NULL);
PRAGMA user_version=2;
'''


def old_database(path):
    with sqlite3.connect(path) as con:
        con.executescript(V2_SCHEMA)
        con.execute("INSERT INTO categories VALUES ('Работа','#123456',1)")
        for eid, source in ((1, 'caldav'), (8, 'manual')):
            con.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        (eid, 'Реальная запись', 'Работа', START, END, START, END, START, END, 'done',
                         'Не потерять', source, f'key:{eid}', START, START))
        con.execute("INSERT INTO calendar_events VALUES (1,'calendar','uid','',0,0,0,0,1)")
        con.execute("INSERT INTO audit VALUES (1,1,'Реальная запись','Импорт Mail.ru','{}',?)", (START,))
        con.execute("INSERT INTO day_freezes VALUES (?,?)", (DAY, START))
        con.execute("INSERT INTO settings VALUES ('ui_theme','dark')")
        con.execute("UPDATE sqlite_sequence SET seq=50 WHERE name='events'")
    return path


def test_v2_migration_keeps_data_links_indexes_sequence_and_a_restorable_backup(tmp_path):
    path = old_database(tmp_path / 'old.db')
    with sqlite3.connect(path) as con:
        before = list(con.execute('SELECT * FROM events ORDER BY id'))
        meta = list(con.execute('SELECT * FROM calendar_events'))
        audit = list(con.execute('SELECT * FROM audit'))
    store = Store(path)
    with sqlite3.connect(path) as con:
        assert list(con.execute('SELECT * FROM events ORDER BY id')) == before
        assert list(con.execute('SELECT * FROM calendar_events')) == meta
        assert list(con.execute('SELECT * FROM audit')) == audit
        assert con.execute('PRAGMA foreign_key_check').fetchall() == []
        assert con.execute('PRAGMA user_version').fetchone()[0] == 3
        assert con.execute("SELECT 1 FROM sqlite_master WHERE name='custom_status_index'").fetchone()
        assert not next(r[3] for r in con.execute('PRAGMA table_info(events)') if r[1] == 'current_start')
    assert store.get_setting('ui_theme') == 'dark' and store.is_frozen(DAY)
    assert [e.id for e in store.daily_events(DAY)] == [1]  # Historical manual records stay archived.
    backups = list((tmp_path / 'backups').glob('*.db'))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as con:
        assert con.execute('PRAGMA user_version').fetchone()[0] == 2
        assert list(con.execute('SELECT * FROM events ORDER BY id')) == before
    assert fact(store) > 50
    Store(path)
    assert len(list((tmp_path / 'backups').glob('*.db'))) == 1


def test_failed_migration_rolls_back_the_original_schema_and_data(tmp_path):
    path = old_database(tmp_path / 'invalid.db')
    with sqlite3.connect(path) as con:
        con.execute("INSERT INTO calendar_events VALUES (999,'calendar','orphan','',0,0,0,0,0)")
        before = list(con.execute('SELECT * FROM events ORDER BY id'))
    with pytest.raises(ValueError, match='связи'):
        Store(path)
    with sqlite3.connect(path) as con:
        assert con.execute('PRAGMA user_version').fetchone()[0] == 2
        assert list(con.execute('SELECT * FROM events ORDER BY id')) == before
        assert next(r[3] for r in con.execute('PRAGMA table_info(events)') if r[1] == 'current_start') == 1
        assert not con.execute("SELECT 1 FROM sqlite_master WHERE name='events_v3'").fetchone()


def test_failed_safety_backup_does_not_start_a_schema_change(tmp_path, monkeypatch):
    path = old_database(tmp_path / 'old.db')
    def fail(*args):
        raise OSError('Cannot write backup')
    monkeypatch.setattr(Store, 'backup', fail)
    with pytest.raises(OSError):
        Store(path)
    with sqlite3.connect(path) as con:
        assert con.execute('PRAGMA user_version').fetchone()[0] == 2
        assert con.execute('SELECT count(*) FROM events').fetchone()[0] == 2
