from dataclasses import replace
import pytest
from director_control.storage import Store
from director_control.backups import validate_database, create_backup, restore_backup
from tests.test_mail_calendar import parse, event


def snapshot(*uids):
    base = parse(*(event(uid) for uid in uids))
    return replace(base, start='2099-10-20T00:00:00', end='2099-11-01T00:00:00',
        events=tuple(replace(e, start=e.start.replace('2026', '2099'), end=e.end.replace('2026', '2099')) for e in base.events))


def test_replacement_withdraws_old_record_and_reappearance_restores_identity(tmp_path):
    store = Store(tmp_path / 'db')
    store.apply_calendar_snapshot(snapshot('old'))
    original = store.daily_events('2099-10-22')[0]
    stats = store.apply_calendar_snapshot(snapshot('new'))
    assert stats['withdrawn'] == 1 and stats['missing'] == 0
    assert len(store.daily_events('2099-10-22')) == 1
    assert store.get_event(original.id).current_start is None
    assert store.day_summary('2099-10-22')['total'] == 1
    assert any(a['action'] == 'Убрано из актуального плана Mail.ru' for a in store.audit_log())
    validate_database(store.path)
    backup = create_backup(store, tmp_path / 'backups')
    restore_backup(store, backup)
    assert store.get_event(original.id).current_start is None
    history = len(store.audit_log())
    assert store.apply_calendar_snapshot(snapshot('new'))['withdrawn'] == 0
    assert len(store.audit_log()) == history
    store.apply_calendar_snapshot(snapshot('old', 'new'))
    assert store.get_event(original.id).current_start == original.current_start
    assert not store.calendar_info()[original.id]['missing']


@pytest.mark.parametrize('protection', ['baseline', 'frozen_day', 'fact', 'status', 'note', 'past'])
def test_protected_records_remain_visible(tmp_path, protection):
    store = Store(tmp_path / 'db')
    initial = parse(event()) if protection == 'past' else snapshot('old')
    store.apply_calendar_snapshot(initial)
    e = store.daily_events(initial.events[0].start[:10])[0]
    if protection == 'baseline':
        store.freeze_day('2099-10-22')
    elif protection == 'frozen_day':
        with store._connect() as con:
            con.execute("INSERT INTO day_freezes VALUES ('2099-10-22','2099-10-20T09:00:00')")
    elif protection == 'fact':
        store.update_event(e.id, actual_start=e.current_start, actual_end=e.current_end)
    elif protection == 'status':
        store.update_event(e.id, status='done')
    elif protection == 'note':
        store.update_event(e.id, note='Keep this')
    stats = store.apply_calendar_snapshot(replace(initial, events=()))
    assert stats['withdrawn'] == 0 and stats['missing'] == 1
    assert store.get_event(e.id).current_start == e.current_start


def test_partial_outside_window_and_previously_missing(tmp_path):
    store = Store(tmp_path / 'db')
    store.apply_calendar_snapshot(snapshot('old'))
    e = store.daily_events('2099-10-22')[0]
    store.apply_calendar_snapshot(replace(snapshot(), unavailable=('unreadable resource',)))
    assert store.get_event(e.id).current_start
    store.apply_calendar_snapshot(replace(snapshot(), start='2099-10-23T00:00:00'))
    assert store.get_event(e.id).current_start
    with store._connect() as con:
        con.execute('UPDATE calendar_events SET missing=1 WHERE event_id=?', (e.id,))
    assert store.apply_calendar_snapshot(snapshot())['withdrawn'] == 1
    assert not store.daily_events('2099-10-22')
    assert store.freeze_day('2099-10-22') == 0
    validate_database(store.path)


def test_unexplained_empty_event_still_fails_backup_validation(tmp_path):
    store = Store(tmp_path / 'db')
    store.apply_calendar_snapshot(snapshot('old'))
    with store._connect() as con:
        con.execute('UPDATE events SET current_start=NULL,current_end=NULL')
    with pytest.raises(ValueError):
        validate_database(store.path)
