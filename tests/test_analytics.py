"""Business rules for period cohorts, provenance and confirmed working time."""
import csv
from datetime import date

import pytest

from director_control.analytics import deviations, export_report, period_bounds
from director_control.mail_calendar import CalendarConfig
from director_control.storage import Store
from tests.helpers import LegacyStoreFixture, seed_event, source_update

DAY = '2026-10-19'


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / 'analytics.db')


def planned(store, day=DAY, title='Работа', start='09:00:00', end='10:00:00', category='Работа', **kwargs):
    return store.create_event(title, category, day + 'T' + start, day + 'T' + end, **kwargs)


@pytest.mark.parametrize('anchor,mode,start,end', [
    ('2026-10-19', 'day', '2026-10-19', '2026-10-20'),
    ('2027-01-01', 'week', '2026-12-28', '2027-01-04'),
    ('2028-02-29', 'month', '2028-02-01', '2028-03-01'),
    ('2026-12-31', 'month', '2026-12-01', '2027-01-01'),
])
def test_calendar_period_boundaries(anchor, mode, start, end):
    assert period_bounds(date.fromisoformat(anchor), mode) == (date.fromisoformat(start), date.fromisoformat(end))


def test_weighted_completion_and_all_statuses(store):
    planned(store, status='done')
    store.freeze_day(DAY)
    statuses = ['pending'] * 5 + ['partial', 'cancelled', 'moved', 'pending']
    for status in statuses:
        planned(store, day='2026-10-20', status=status)
    store.freeze_day('2026-10-20')
    report = store.analytics_report(DAY)
    assert report.totals.planned == 10 and report.totals.done == 1
    assert report.totals.completion_percent == 10
    assert report.totals.partial == report.totals.cancelled == report.totals.moved == 1
    assert report.totals.missing_time == 1
    assert report.daily[date(2026, 10, 19)].completion_percent == 100
    assert report.daily[date(2026, 10, 20)].completion_percent == 0


def test_unplanned_share_uses_confirmed_time_and_unknown_is_explicit(store):
    planned(store, actual_start=DAY+'T09:00:00', actual_end=DAY+'T10:00:00', status='done')
    store.freeze_day(DAY)
    planned(store, start='10:00:00', end='11:00:00', actual_start=DAY+'T10:00:00', actual_end=DAY+'T10:30:00', status='partial')
    planned(store, day='2026-10-20', actual_start='2026-10-20T09:00:00', actual_end='2026-10-20T09:30:00', status='done')
    planned(store, start='15:00:00', end='16:00:00', actual_start=DAY+'T15:00:00', actual_end=DAY+'T16:00:00', status='cancelled')
    planned(store, start='16:00:00', end='17:00:00', actual_start=DAY+'T16:00:00', actual_end=DAY+'T17:00:00')
    m = store.analytics_report(DAY).totals
    assert m.actual_seconds == 120 * 60
    assert m.unplanned_seconds == m.unknown_seconds == 30 * 60
    assert m.unplanned_percent == 25
    assert m.comparable == 1


def test_postfactum_never_enters_plan_and_legacy_is_hidden(store):
    post = store.create_event('Срочная работа', 'Работа', actual_start=DAY+'T09:00:00', actual_end=DAY+'T10:00:00')
    seed_event(store, 'Старая запись', 'Работа', DAY+'T10:00:00', DAY+'T11:00:00', source='manual')
    before = store.analytics_report(DAY)
    store.freeze_day(DAY)
    after = store.analytics_report(DAY)
    for r in (before, after):
        assert r.totals.planned == 0 and r.totals.unplanned_percent == 100
        assert [row.event.id for row in r.events] == [post]


def test_intervals_are_clipped_at_midnight_and_month_end_without_duplicate_counts(store):
    eid = store.create_event('Ночная работа', 'Работа', '2026-10-31T23:00:00', '2026-11-01T01:00:00',
                             actual_start='2026-10-31T23:30:00', actual_end='2026-11-01T01:30:00', status='done')
    store.freeze_day('2026-10-31')
    october, november = (store.analytics_report(d, 'month') for d in ('2026-10-31', '2026-11-01'))
    assert october.totals.planned_seconds == november.totals.planned_seconds == 3600
    assert october.totals.actual_seconds == 1800 and november.totals.actual_seconds == 5400
    assert october.totals.planned == october.totals.comparable == 1
    assert november.totals.planned == november.totals.comparable == 0
    assert october.events[0].event.id == november.events[0].event.id == eid
    assert october.events[0].duration_delta == november.events[0].duration_delta == 0


def test_moved_import_keeps_plan_origin_outside_period(store):
    eid = seed_event(store, 'Перенос', 'Работа', '2026-10-16T09:00:00', '2026-10-16T10:00:00')
    store.freeze_day('2026-10-16')
    source_update(store, eid, current_start=DAY+'T09:00:00', current_end=DAY+'T10:00:00',
                  actual_start=DAY+'T09:00:00', actual_end=DAY+'T10:00:00', status='done')
    r = store.analytics_report(DAY)
    assert r.totals.planned == 0 and r.totals.actual_seconds == 3600
    assert r.totals.unplanned_seconds == r.totals.unknown_seconds == 0
    assert r.events[0].origin == 'planned' and r.events[0].start_delta == 3 * 24 * 60
    assert r.totals.comparable == 1


def test_absolute_means_do_not_cancel_and_tolerance_is_frozen(store):
    first = planned(store, actual_start=DAY+'T09:20:00', actual_end=DAY+'T10:40:00', status='done')
    second = planned(store, start='11:00:00', end='12:00:00', actual_start=DAY+'T10:40:00', actual_end=DAY+'T11:20:00', status='partial')
    store.freeze_day(DAY)
    store.set_setting('tolerance_minutes', '60')
    r = store.analytics_report(DAY)
    assert deviations(store.get_event(first)) == (20, 20)
    assert deviations(store.get_event(second)) == (-20, -20)
    assert r.totals.mean_start_minutes == r.totals.mean_duration_minutes == 20
    assert r.totals.start_outside == r.totals.duration_outside == 2
    assert all(row.tolerance == 10 for row in r.events)


def test_category_scope_uses_frozen_tracking_and_original_category(store):
    eid = planned(store, actual_start=DAY+'T09:00:00', actual_end=DAY+'T10:00:00', status='done')
    road = planned(store, category='Дорога', start='10:00:00', end='11:00:00', status='done')
    store.freeze_day(DAY)
    store.set_category_tracking('Работа', False)
    store.set_category_tracking('Дорога', True)
    store.update_event(eid, category='Отдых')
    r = store.analytics_report(DAY)
    assert r.totals.planned == 1 and [x.event.id for x in r.events] == [eid]
    assert ('Работа', 60, 0) in r.categories and ('Отдых', 0, 60) in r.categories
    assert store.analytics_report(DAY, only_tracked=False).totals.planned == 2
    assert road not in [x.event.id for x in r.events]


def test_all_day_has_no_invented_hours_or_missing_time(store):
    eid = seed_event(store, 'Весь день', 'Работа', DAY+'T00:00:00', '2026-10-20T00:00:00')
    with store._connect() as con:
        con.execute('UPDATE calendar_events SET all_day=1 WHERE event_id=?', (eid,))
    store.update_event(eid, status='done')
    store.freeze_day(DAY)
    r = store.analytics_report(DAY)
    assert r.totals.planned == r.totals.done == 1
    assert r.totals.planned_seconds == r.totals.actual_seconds == r.totals.missing_time == r.totals.comparable == 0


def test_overlap_warning_counts_excess_over_union(store):
    for start, end in (('09:00:00', '11:00:00'), ('10:00:00', '12:00:00'), ('10:30:00', '11:00:00')):
        store.create_event('Срочное', 'Работа', actual_start=DAY+'T'+start, actual_end=DAY+'T'+end)
    m = store.analytics_report(DAY).totals
    assert m.actual_seconds == 270 * 60 and m.overlap_seconds == 90 * 60
    assert m.unplanned_percent == 100


def test_seconds_are_preserved_and_csv_summary_is_weighted(store, tmp_path):
    planned(store, actual_start=DAY+'T09:00:30', actual_end=DAY+'T09:01:00', status='done')
    planned(store, day='2026-10-20')
    planned(store, day='2026-10-20')
    store.freeze_day(DAY)
    store.freeze_day('2026-10-20')
    r = store.analytics_report(DAY)
    assert r.totals.actual_seconds == 30
    assert r.totals.mean_start_minutes == .5
    out = tmp_path / 'report.csv'
    export_report(r, out)
    assert out.read_bytes().startswith(b'\xef\xbb\xbf')
    with out.open(encoding='utf-8-sig') as stream:
        rows = list(csv.DictReader(stream, delimiter=';'))
    assert len(rows) == 8
    assert rows[0]['Исполнение, %'] == '33,33'
    assert rows[0]['Факт, мин'] == '0,50'
    assert rows[0]['Дней с зафиксированным планом'] == '2'
    assert rows[1]['Исполнение, %'] == '100,00'
    assert rows[-1]['Исполнение, %'] == ''


def test_empty_period_has_undefined_ratios_and_no_comparisons(store):
    m = store.analytics_report(DAY).totals
    assert m.completion_percent is m.unplanned_percent is m.mean_start_minutes is m.mean_duration_minutes is None
    with pytest.raises(ValueError):
        store.analytics_report(DAY, 'year')


def test_sync_coverage_is_per_calendar_and_latest_attempt_for_each_day(store):
    url, login = 'https://calendar.mail.ru/principals/test/calendars/example/', 'test@example.test'
    config = CalendarConfig(url, login)
    store.set_setting('mail_url', url)
    store.set_setting('mail_login', login)
    with store._connect() as con:
        for key, start, end, status in ((config.calendar_key, DAY, '2026-10-26', 'complete'),
                                      ('another', DAY, '2026-10-26', 'failed'),
                                      (config.calendar_key, '2026-10-20', '2026-10-21', 'failed')):
            con.execute('INSERT INTO calendar_syncs(calendar_key,start,end,status,finished_at) VALUES (?,?,?,?,?)',
                        (key, start+'T00:00:00', end+'T00:00:00', status, '2026-10-01T10:00:00'))
    eid = seed_event(store, 'Проверить источник', 'Работа', DAY+'T09:00:00', DAY+'T10:00:00')
    with store._connect() as con:
        con.execute('UPDATE calendar_events SET missing=1 WHERE event_id=?', (eid,))
    r = store.analytics_report(DAY)
    assert r.loaded_days == 6 and r.source_warnings == 1
    assert r.events[0].source_warning


def test_report_is_read_only_and_does_not_freeze_plan_or_invent_fact(store):
    eid = planned(store)
    LegacyStoreFixture.update_event(store, eid, status='done')  # Historical record, before auto fact.
    audit = store.audit_log()
    before = store.path.read_bytes()
    r = store.analytics_report(DAY)
    assert r.totals.missing_time == 1 and r.totals.actual_seconds == 0
    assert store.path.read_bytes() == before
    assert store.audit_log() == audit and not store.is_frozen(DAY)
    assert r.totals.planned == 0
