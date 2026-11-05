"""Consistent interpretation of cancellation and a bounded source absence."""
from dataclasses import replace

import pytest

from director_control.backups import create_backup, restore_backup
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
