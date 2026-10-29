from datetime import date

import pytest

from director_control.analytics import build_report, export_report
from director_control.storage import Store


@pytest.mark.parametrize('kind,expected', [('moved', 'planned'), ('unfixed', 'unfixed'),
                                         ('late', 'unplanned'), ('postfactum', 'unplanned')])
def test_calendar_report_and_csv_agree(tmp_path, kind, expected):
    store = Store(tmp_path / 'db')
    day = '2026-10-29'
    if kind == 'late':
        store.freeze_day(day)
    if kind == 'postfactum':
        eid = store.create_event('Работа', 'Работа', actual_start=day+'T09:00:00', actual_end=day+'T10:00:00')
    else:
        original = '2026-09-30' if kind == 'moved' else day
        eid = store.create_event('Работа', 'Работа', original+'T09:00:00', original+'T10:00:00')
        if kind == 'moved':
            store.freeze_day(original)
        store.update_event(eid, current_start=day+'T09:00:00', current_end=day+'T10:00:00',
                           actual_start=day+'T09:00:00', actual_end=day+'T10:00:00', status='done')
    frozen = {d for d in (day, '2026-09-30') if store.is_frozen(d)}
    report = build_report(date.fromisoformat(day), 'day', True, store.daily_events(day),
                         store.categories(), store.baseline_rules(), {}, frozen, [])
    summary = store.day_summary(day)
    assert report.events[0].origin == expected
    assert summary['unplanned'] == (expected == 'unplanned')
    assert summary['unfixed'] == (expected == 'unfixed')
    assert report.totals.unplanned_seconds == (3600 if expected == 'unplanned' else 0)
    assert report.totals.unknown_seconds == (3600 if expected == 'unfixed' else 0)
    export_report(report, tmp_path / 'report.csv')
    import csv
    with (tmp_path / 'report.csv').open(encoding='utf-8-sig') as stream:
        row = next(csv.DictReader(stream, delimiter=';'))
    assert row['Вне плана, мин'] == ('60,00' if expected == 'unplanned' else '0,00')
    if kind == 'moved':
        store.set_category_tracking('Работа', False)
        assert store.day_summary(day)['nontracked'] == 0
        assert store.day_summary('2026-09-30')['planned'] == 1
