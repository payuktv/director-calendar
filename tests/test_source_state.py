"""Consistent interpretation of cancellation and a bounded source absence."""
from dataclasses import replace

import pytest

from director_control.backups import create_backup, restore_backup
from director_control.mail_calendar import CalendarSnapshot, RemoteEvent
from director_control.source_state import source_state
from director_control.storage import Event, Store
from tests.test_mail_calendar import event, parse


@pytest.mark.parametrize('status,metadata,code,review', [
    ('pending', {}, 'present', False),
    ('cancelled', {'local_status': 1}, 'cancelled_locally', False),
    ('cancelled', {'missing': 1, 'local_status': 1}, 'cancelled_missing', False),
    ('cancelled', {'missing': 1, 'cancelled': 1}, 'cancelled_missing', False),
    ('pending', {'missing': 1}, 'missing', True),
    ('done', {'missing': 1, 'local_status': 1}, 'missing', True),
    ('partial', {'missing': 1}, 'missing', True),
    ('moved', {'missing': 1}, 'missing', True),
    ('cancelled', {'cancelled': 1}, 'cancelled_in_source', False),
    ('done', {'cancelled': 1, 'local_status': 1}, 'source_cancelled_conflict', True),
])
def test_state_distinguishes_expected_cancellation_from_unresolved_changes(status, metadata, code, review):
    item = Event(1, 'Synthetic', 'Работа', '2026-10-22T09:00:00', '2026-10-22T10:00:00',
                 None, None, None, None, status, '', 'caldav')
    state = source_state(item, metadata)
    assert state.code == code and state.needs_review == review


@pytest.mark.parametrize('frozen', [False, True])
def test_cancel_then_delete_is_resolved_without_erasing_the_original_record(tmp_path, frozen):
    store = Store(tmp_path/'db')
    initial = parse(event())
    store.apply_calendar_snapshot(initial)
    original = store.daily_events('2026-10-22')[0]
    if frozen:
        store.freeze_day('2026-10-22')
    store.update_event(original.id, status='cancelled', note='Meeting cancelled')
    saved = store.get_event(original.id)
    stats = store.apply_calendar_snapshot(replace(initial, events=()))
    assert stats['missing'] == stats['withdrawn'] == 0
    retained = store.get_event(original.id)
    assert replace(retained, revision=saved.revision) == saved
    assert store.calendar_info()[original.id]['missing'] == 1
    report = store.analytics_report('2026-10-22', 'day', only_tracked=False)
    assert report.source_warnings == 0 and report.totals.actual_seconds == 0
    assert report.totals.planned == report.totals.cancelled == int(frozen)
    assert store.audit_log()[0]['action'] == 'Отменённое событие отсутствует в Mail.ru'
    count = len(store.audit_log())
    store.apply_calendar_snapshot(replace(initial, events=()))
    assert len(store.audit_log()) == count
    backup = create_backup(store)
    restore_backup(store, backup)
    assert store.get_event(original.id).status == 'cancelled'
    assert store.analytics_report('2026-10-22', 'day', only_tracked=False).source_warnings == 0
    # Source reappearance never silently reactivates a local cancellation.
    store.apply_calendar_snapshot(initial)
    assert store.get_event(original.id).status == 'cancelled'
    assert source_state(store.get_event(original.id), store.calendar_info()[original.id]).code == 'cancelled_locally'


def test_cancellation_after_missing_resolves_warning_and_undo_restores_it(tmp_path):
    store = Store(tmp_path/'db')
    initial = parse(event())
    store.apply_calendar_snapshot(initial)
    original = store.daily_events('2026-10-22')[0]
    absent = replace(initial, events=())
    assert store.apply_calendar_snapshot(absent)['missing'] == 1
    store.update_event(original.id, status='cancelled')
    assert store.analytics_report('2026-10-22', 'day', only_tracked=False).source_warnings == 0
    assert store.apply_calendar_snapshot(absent)['missing'] == 0
    store.update_event(original.id, status='pending')
    assert store.apply_calendar_snapshot(absent)['missing'] == 1
    assert store.analytics_report('2026-10-22', 'day', only_tracked=False).source_warnings == 1


def test_partial_result_does_not_claim_the_source_absence_was_confirmed(tmp_path):
    store = Store(tmp_path/'db')
    initial = parse(event())
    store.apply_calendar_snapshot(initial)
    original = store.daily_events('2026-10-22')[0]
    store.update_event(original.id, status='cancelled')
    store.apply_calendar_snapshot(replace(initial, events=(), unavailable=('unreadable child',)))
    assert store.calendar_info()[original.id]['missing'] == 0
    assert source_state(store.get_event(original.id), store.calendar_info()[original.id]).code == 'cancelled_locally'


def test_cancelled_source_conflict_count_matches_analytics(tmp_path):
    store = Store(tmp_path/'db')
    initial = parse(event())
    store.apply_calendar_snapshot(initial)
    original = store.daily_events('2026-10-22')[0]
    store.update_event(original.id, status='done', actual_start=original.current_start, actual_end=original.current_end)
    changed = replace(initial, events=(replace(initial.events[0], cancelled=True),))
    assert store.apply_calendar_snapshot(changed)['missing'] == 1
    assert store.analytics_report('2026-10-22', 'day', only_tracked=False).source_warnings == 1
    assert store.get_event(original.id).status == 'done'


def test_review_list_matches_sync_across_dates_and_distinguishes_duplicate_titles(tmp_path):
    store = Store(tmp_path / 'db')
    day = RemoteEvent('day', 'day', '', 'Совещание', '2099-11-01T00:00:00', '2099-11-02T00:00:00', all_day=True)
    later = RemoteEvent('later', 'later', '', 'Совещание', '2099-11-10T11:00:00', '2099-11-10T12:00:00')
    first = CalendarSnapshot('calendar-one', '2099-11-01T00:00:00', '2099-12-01T00:00:00', (later, day))
    store.apply_calendar_snapshot(first)
    day_id = store.daily_events('2099-11-01')[0].id
    later_id = store.daily_events('2099-11-10')[0].id
    store.update_event(day_id, note='Keep the local details')
    store.update_event(later_id, status='done')
    absent = replace(first, events=(replace(later, cancelled=True),))
    assert store.apply_calendar_snapshot(replace(absent, unavailable=('unreadable resource',)))['missing'] == 1
    assert [item.event.id for item in store.mail_review_items(first.calendar_key)] == [later_id]
    assert store.apply_calendar_snapshot(absent)['missing'] == 2
    other = replace(first, calendar_key='calendar-two', events=(replace(later, key='other', uid='other'),))
    store.apply_calendar_snapshot(other)
    other_id = next(e.id for e in store.daily_events('2099-11-10') if e.id != later_id)
    store.update_event(other_id, note='Keep')
    assert store.apply_calendar_snapshot(replace(other, events=()))['missing'] == 1

    december = replace(first, start=first.end, end='2100-01-01T00:00:00', events=())
    count = store.apply_calendar_snapshot(december)['missing']
    items = store.mail_review_items(first.calendar_key)
    assert count == store.mail_review_count(first.calendar_key) == len(items) == 2
    assert [(item.event.id, item.state.code, item.all_day) for item in items] == [
        (day_id, 'missing', True), (later_id, 'source_cancelled_conflict', False)]
    assert all(item.event.title == 'Совещание' and item.state.warning for item in items)
    assert [item.event.id for item in store.mail_review_items(other.calendar_key)] == [other_id]

    store.update_event(day_id, status='cancelled')
    assert [item.event.id for item in store.mail_review_items(first.calendar_key)] == [later_id]
    assert store.apply_calendar_snapshot(first)['missing'] == store.mail_review_count(first.calendar_key) == 0
    assert not store.mail_review_items(first.calendar_key)
    assert store.mail_review_count(other.calendar_key) == 1
