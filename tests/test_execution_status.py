"""Completion defaults and explicit failure attribution across storage/reporting."""
import csv
import json
from dataclasses import replace

import pytest

from director_control.analytics import export_report
from director_control.backups import create_backup, restore_backup
from director_control.recovery import recover_database
from director_control.storage import EventConflictError, STATUSES, Store
from director_control.source_state import source_state
from director_control.updates import prepare_version_update
from tests.helpers import LegacyStoreFixture, seed_event, source_update
from tests.test_mail_calendar import event, parse

DAY = '2026-10-22'
START, END = DAY + 'T09:00:00', DAY + 'T10:00:00'


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / 'execution.db')


@pytest.mark.parametrize('source', ['local', 'caldav'])
def test_completion_fills_current_interval_in_one_audited_revision(store, source):
    eid = (store.create_event('Task', 'Работа', START, END) if source == 'local'
           else seed_event(store, 'Task', 'Работа', START, END))
    store.freeze_day(DAY)
    later = dict(current_start=DAY+'T11:00:00', current_end=DAY+'T12:30:00')
    source_update(store, eid, **later)
    before = store.get_event(eid)
    audit_count = len(store.audit_log())
    store.update_event(eid, expected_revision=before.revision, status='done')
    saved = store.get_event(eid)
    assert (saved.actual_start, saved.actual_end) == (later['current_start'], later['current_end'])
    assert (saved.baseline_start, saved.baseline_end) == (START, END)
    assert saved.revision == before.revision + 1
    assert len(store.audit_log()) == audit_count + 1
    details = json.loads(store.audit_log()[0]['details'])
    assert set(details) == {'status', 'actual_start', 'actual_end'}
    assert details['actual_start'] == {'было': None, 'стало': saved.actual_start}
    if source == 'caldav':
        assert store.calendar_info()[eid]['local_status'] == 1
    with pytest.raises(EventConflictError):
        store.update_event(eid, expected_revision=before.revision, status='failed_director')
    assert store.get_event(eid) == saved


def test_creation_completion_and_manual_correction_preserve_seconds(store):
    eid = store.create_event('Task', 'Работа', START, END, status='done')
    assert store.get_event(eid).actual_start == START
    actual = dict(actual_start=DAY+'T09:03:24', actual_end=DAY+'T09:45:30')
    store.update_event(eid, **actual)
    for status in ('partial', 'failed_assistant', 'pending', 'done'):
        store.update_event(eid, status=status)
        saved = store.get_event(eid)
        assert (saved.actual_start, saved.actual_end) == (actual['actual_start'], actual['actual_end'])
    store.update_event(eid, current_start=DAY+'T14:00:00', current_end=DAY+'T15:00:00', status='done')
    assert store.get_event(eid).actual_start == actual['actual_start']


def test_explicit_fact_wins_and_incomplete_pair_rolls_back(store):
    eid = store.create_event('Task', 'Работа', START, END)
    before, audit = store.get_event(eid), store.audit_log()
    with pytest.raises(ValueError):
        store.update_event(eid, status='done', actual_start=START)
    assert store.get_event(eid) == before and store.audit_log() == audit
    with pytest.raises(ValueError):
        store.create_event('Task', 'Работа', START, END, status='done', actual_end=END)
    store.update_event(eid, status='done', actual_start=DAY+'T09:05:00', actual_end=DAY+'T09:30:00')
    assert store.get_event(eid).actual_end == DAY+'T09:30:00'


def test_partial_waits_for_fact_and_legacy_done_is_not_backfilled_by_read_or_note(store):
    partial = store.create_event('Partial', 'Работа', START, END, status='partial')
    legacy = store.create_event('Historical', 'Работа', START, END)
    LegacyStoreFixture.update_event(store, legacy, status='done')
    store.update_event(legacy, note='Keep history')
    reopened = Store(store.path)
    report = reopened.analytics_report(DAY, 'day')
    assert report.totals.missing_time == 2 and report.totals.actual_seconds == 0
    assert all(row.missing_time for row in report.events)
    assert reopened.get_event(legacy).actual_start is None
    reopened.update_event(partial, actual_start=START, actual_end=DAY+'T09:20:00')
    report = reopened.analytics_report(DAY, 'day')
    assert report.totals.missing_time == 1 and report.totals.actual_seconds == 20 * 60


@pytest.mark.parametrize('status', ['done', 'partial'])
def test_all_day_neither_invents_hours_nor_requires_fact(store, status):
    eid = seed_event(store, 'All day', 'Работа', DAY+'T00:00:00', '2026-10-23T00:00:00')
    with store._connect() as con:
        con.execute('UPDATE calendar_events SET all_day=1 WHERE event_id=?', (eid,))
    store.freeze_day(DAY)
    store.update_event(eid, status=status)
    assert store.get_event(eid).actual_start is None
    m = store.analytics_report(DAY, 'day').totals
    assert m.actual_seconds == m.missing_time == 0


@pytest.mark.parametrize('status', ['failed_assistant', 'failed_director'])
@pytest.mark.parametrize('frozen', [False, True])
def test_failure_survives_source_deletion_cancellation_and_reappearance(store, status, frozen):
    initial = parse(event())
    store.apply_calendar_snapshot(initial)
    eid = store.daily_events(DAY)[0].id
    if frozen:
        store.freeze_day(DAY)
    store.update_event(eid, status=status, note='Forgot the meeting')
    saved = store.get_event(eid)
    for snapshot in (replace(initial, events=()),
                     replace(initial, events=tuple(replace(e, cancelled=True) for e in initial.events)), initial):
        assert store.apply_calendar_snapshot(snapshot)['missing'] == 0
        assert replace(store.get_event(eid), revision=saved.revision) == saved
        assert not source_state(store.get_event(eid), store.calendar_info()[eid]).needs_review
        report = store.analytics_report(DAY, 'day', only_tracked=False)
        assert report.totals.failed_total == 1 and report.totals.failed == int(frozen)
        assert report.totals.actual_seconds == report.totals.cancelled_total == report.source_warnings == 0
    store.update_event(eid, status='pending')
    assert store.apply_calendar_snapshot(replace(initial, events=()))['missing'] == 1


@pytest.mark.parametrize('mode', ['normal', 'emergency'])
def test_new_statuses_and_auto_fact_survive_restore_and_startup(store, tmp_path, mode):
    ids = [store.create_event(status, 'Работа', START, END, status=status) for status in STATUSES]
    store.freeze_day(DAY)
    copy = create_backup(store)
    live = Store(tmp_path / 'restored.db')
    if mode == 'normal':
        restore_backup(live, copy)
    else:
        live.path.write_bytes(b'damaged')
        recover_database(live.path, copy)
    prepare_version_update(live.path)
    restored = Store(live.path)
    assert [restored.get_event(eid) for eid in ids] == [store.get_event(eid) for eid in ids]
    assert restored.analytics_report(DAY, 'day').totals.failed_total == 2


def test_failure_statistics_include_unfixed_days_but_keep_plan_denominator(store, tmp_path):
    for status in STATUSES:
        store.create_event(status, 'Работа', START, END, status=status)
    store.freeze_day(DAY)
    store.create_event('Unfixed failure', 'Работа', '2026-10-23T09:00:00', '2026-10-23T10:00:00', status='failed_director')
    store.create_event('Unfixed cancellation', 'Работа', '2026-10-23T09:00:00', '2026-10-23T10:00:00', status='cancelled')
    report = store.analytics_report(DAY)
    m = report.totals
    assert m.planned == 7 and m.completion_percent == pytest.approx(100 / 7)
    assert m.failed == 2 and m.failed_total == 3
    assert m.failed_assistant_total == 1 and m.failed_director_total == 2
    assert m.cancelled == 1 and m.cancelled_total == 2
    assert m.planned == m.done + m.partial + m.pending + m.cancelled + m.moved + m.failed
    assert m.actual_seconds == 3600 and m.missing_time == 1
    path = tmp_path / 'report.csv'
    export_report(report, path)
    with path.open(encoding='utf-8-sig') as stream:
        rows = list(csv.DictReader(stream, delimiter=';'))
    assert rows[0]['Провалено всего'] == '3'
    assert rows[0]['Провалено — ассистент'] == '1'
    assert rows[0]['Провалено — директор'] == '2'
    assert rows[0]['Отменено всего'] == '2'
    assert all(None not in row for row in rows)


def test_failures_count_once_by_original_date_and_respect_frozen_tracking(store):
    eid = store.create_event('Overnight', 'Работа', '2026-10-31T23:00:00', '2026-11-01T01:00:00')
    road = store.create_event('Road', 'Дорога', '2026-10-31T23:00:00', '2026-11-01T01:00:00')
    store.freeze_day('2026-10-31')
    store.set_category_tracking('Работа', False)
    store.set_category_tracking('Дорога', True)
    for target in (eid, road):
        store.update_event(target, status='failed_assistant', current_start='2026-11-02T09:00:00', current_end='2026-11-02T10:00:00')
    assert store.analytics_report('2026-10-31', 'month').totals.failed_total == 1
    assert store.analytics_report('2026-10-31', 'month', only_tracked=False).totals.failed_total == 2
    assert store.analytics_report('2026-11-01', 'month', only_tracked=False).totals.failed_total == 0


def test_failures_do_not_occupy_calendar_work_coverage(store):
    eid = store.create_event('Task', 'Работа', START, END)
    pending = store.coverage_for_day(DAY)
    store.update_event(eid, status='failed_assistant')
    failed = store.coverage_for_day(DAY)
    assert pending != failed
    store.update_event(eid, status='cancelled')
    assert failed == store.coverage_for_day(DAY)


def test_distribution_execution_acceptance(tmp_path):
    from director_control.distribution_check import _verify_execution_status
    _verify_execution_status(tmp_path)
