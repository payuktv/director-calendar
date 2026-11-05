"""Period analytics from a consistent storage snapshot; no GUI or database writes."""
from __future__ import annotations

import csv
from dataclasses import dataclass, fields
from datetime import date, datetime, time, timedelta
from pathlib import Path

from .storage import Event
from .provenance import work_origin
from .source_state import source_state


def period_bounds(anchor: date, mode: str) -> tuple[date, date]:
    """Return a calendar interval with an exclusive end."""
    if mode == 'day':
        return anchor, anchor + timedelta(days=1)
    if mode == 'week':
        start = anchor - timedelta(days=anchor.weekday())
        return start, start + timedelta(days=7)
    if mode == 'month':
        start = anchor.replace(day=1)
        return start, date(start.year + (start.month == 12), start.month % 12 + 1, 1)
    raise ValueError('Неизвестный период аналитики')


def interval(start: str | None, end: str | None):
    return (datetime.fromisoformat(start), datetime.fromisoformat(end)) if start and end else None


def clipped_seconds(span, start: datetime, end: datetime) -> float:
    return max(0., (min(span[1], end) - max(span[0], start)).total_seconds()) if span else 0.


def deviations(event: Event) -> tuple[float | None, float | None]:
    """Signed minutes: actual start minus baseline, actual duration minus baseline."""
    plan = interval(event.baseline_start, event.baseline_end)
    actual = interval(event.actual_start, event.actual_end)
    if not plan or not actual or event.status not in {'done', 'partial'}:
        return None, None
    return ((actual[0] - plan[0]).total_seconds() / 60,
            ((actual[1] - actual[0]) - (plan[1] - plan[0])).total_seconds() / 60)


@dataclass
class Metrics:
    planned: int = 0
    done: int = 0
    partial: int = 0
    cancelled: int = 0
    moved: int = 0
    pending: int = 0
    completed: int = 0
    missing_time: int = 0
    comparable: int = 0
    start_outside: int = 0
    duration_outside: int = 0
    planned_seconds: float = 0.
    actual_seconds: float = 0.
    unplanned_seconds: float = 0.
    unknown_seconds: float = 0.
    abs_start_seconds: float = 0.
    abs_duration_seconds: float = 0.
    overlap_seconds: float = 0.

    @property
    def completion_percent(self):
        return self.done / self.planned * 100 if self.planned else None

    @property
    def unplanned_percent(self):
        return self.unplanned_seconds / self.actual_seconds * 100 if self.actual_seconds else None

    @property
    def mean_start_minutes(self):
        return self.abs_start_seconds / self.comparable / 60 if self.comparable else None

    @property
    def mean_duration_minutes(self):
        return self.abs_duration_seconds / self.comparable / 60 if self.comparable else None


@dataclass(frozen=True)
class EventMeasure:
    event: Event
    origin: str
    baseline_category: str
    planned_seconds: float
    actual_seconds: float
    start_delta: float | None
    duration_delta: float | None
    tolerance: int
    missing_time: bool
    in_comparison: bool
    all_day: bool
    source_warning: str

    @property
    def outside_tolerance(self):
        return self.start_delta is not None and (
            abs(self.start_delta) > self.tolerance or abs(self.duration_delta) > self.tolerance)


@dataclass(frozen=True)
class Report:
    start: date
    end: date
    mode: str
    only_tracked: bool
    totals: Metrics
    daily: dict[date, Metrics]
    events: tuple[EventMeasure, ...]
    categories: tuple[tuple[str, float, float], ...]
    frozen_days: int
    loaded_days: int | None

    @property
    def source_warnings(self):
        return sum(bool(row.source_warning) for row in self.events)


def _overlap_seconds(spans):
    """Excess over interval union: count simultaneous time explicitly."""
    total = sum((end - start).total_seconds() for start, end in spans)
    union, cursor = 0., None
    for start, end in sorted(spans):
        union += max(0., (end - max(start, cursor or start)).total_seconds())
        cursor = max(cursor or end, end)
    return max(0., total - union)


def build_report(anchor, mode, only_tracked, events, categories, rules, metadata, frozen, syncs, calendar_key=None):
    start, end = period_bounds(anchor, mode)
    begin, finish = datetime.combine(start, time.min), datetime.combine(end, time.min)
    daily = {start + timedelta(days=i): Metrics() for i in range((end - start).days)}
    spans = {day: [] for day in daily}
    tracking = {c['name']: bool(c['track']) for c in categories}
    category_time, measures = {}, []

    for event in events:
        rule, meta = rules.get(event.id, {}), metadata.get(event.id, {})
        if only_tracked and not (rule.get('track', tracking.get(event.category, True))):
            continue
        plan = interval(event.baseline_start, event.baseline_end)
        actual = interval(event.actual_start, event.actual_end) if event.status in {'done', 'partial'} else None
        all_day = bool(meta.get('baseline_all_day') if plan else meta.get('all_day'))
        plan_time = clipped_seconds(plan, begin, finish) if not all_day else 0.
        fact_time = clipped_seconds(actual, begin, finish)
        baseline_category = rule.get('category', event.category)
        origin = work_origin(event, frozen)
        # Count tasks once, by the date of the original plan. Times may span days.
        if plan and plan[0].date() in daily:
            bucket = daily[plan[0].date()]
            bucket.planned += 1
            setattr(bucket, event.status, getattr(bucket, event.status) + 1)
        completed_date = (event.actual_start or event.baseline_start or event.current_start or '')[:10]
        if event.status == 'done' and completed_date and date.fromisoformat(completed_date) in daily:
            daily[date.fromisoformat(completed_date)].completed += 1
        missing_date = (event.baseline_start or event.current_start or '')[:10]
        missing = (event.status == 'done' and not (event.actual_start and event.actual_end)
                   and not meta.get('all_day') and bool(missing_date)
                   and date.fromisoformat(missing_date) in daily)
        if missing:
            daily[date.fromisoformat(missing_date)].missing_time += 1
        start_delta, duration_delta = (None, None) if all_day else deviations(event)
        comparable = bool(start_delta is not None and actual[0].date() in daily)
        tolerance = rule.get('tolerance_minutes', 10)
        if comparable:
            bucket = daily[actual[0].date()]
            bucket.comparable += 1
            bucket.abs_start_seconds += abs(start_delta) * 60
            bucket.abs_duration_seconds += abs(duration_delta) * 60
            bucket.start_outside += abs(start_delta) > tolerance
            bucket.duration_outside += abs(duration_delta) > tolerance
        for day, bucket in daily.items():
            ds = datetime.combine(day, time.min)
            de = ds + timedelta(days=1)
            bucket.planned_seconds += clipped_seconds(plan, ds, de) if not all_day else 0.
            seconds = clipped_seconds(actual, ds, de)
            bucket.actual_seconds += seconds
            if origin == 'unplanned':
                bucket.unplanned_seconds += seconds
            elif origin == 'unfixed':
                bucket.unknown_seconds += seconds
            if seconds:
                spans[day].append((max(actual[0], ds), min(actual[1], de)))
        if plan_time:
            category_time.setdefault(baseline_category, [0., 0.])[0] += plan_time / 60
        if fact_time:
            category_time.setdefault(event.category, [0., 0.])[1] += fact_time / 60
        warning = source_state(event, meta).warning
        measures.append(EventMeasure(event, origin, baseline_category, plan_time, fact_time,
                                     start_delta, duration_delta, tolerance, missing, comparable, all_day, warning))

    for day, bucket in daily.items():
        bucket.overlap_seconds = _overlap_seconds(spans[day])
    totals = Metrics(**{f.name: sum(getattr(m, f.name) for m in daily.values()) for f in fields(Metrics)})
    loaded = None
    if calendar_key is not None:
        loaded = 0
        for day in daily:
            ds, de = day.isoformat() + 'T00:00:00', (day + timedelta(days=1)).isoformat() + 'T00:00:00'
            matches = [s for s in syncs if s['calendar_key'] == calendar_key and s['start'] <= ds and s['end'] >= de]
            loaded += bool(matches and max(matches, key=lambda s: s['id'])['status'] == 'complete')
    return Report(start, end, mode, only_tracked, totals, daily, tuple(measures),
                  tuple((name, *values) for name, values in sorted(category_time.items(), key=lambda r: -sum(r[1]))),
                  sum(d.isoformat() in frozen for d in daily), loaded)


def export_report(report: Report, destination: Path | str):
    """Weighted period summary and additive daily data, suitable for Russian Excel."""
    headers = ['Строка', 'С', 'По', 'Категории', 'В плане', 'Выполнено из плана',
               'Выполнено по дате факта/плана', 'Частично', 'Отменено', 'Перенесено', 'Не подтверждено',
               'Исполнение, %', 'План, мин', 'Факт, мин', 'Вне плана, мин', 'План не зафиксирован, мин',
               'Доля внепланового, %', 'Доля — нижняя граница', 'Выполнено без времени', 'Сравнимых событий',
               'Среднее абсолютное отклонение начала, мин', 'Среднее абсолютное отклонение длительности, мин',
               'Начало вне допуска', 'Длительность вне допуска', 'Повторно учтено при пересечениях, мин',
               'Дней с зафиксированным планом', 'Дней с полной загрузкой Mail.ru', 'Дней в периоде',
               'Событий с предупреждением источника']

    def row(label, start, end, m, summary=False):
        return [label, start.isoformat(), (end - timedelta(days=1)).isoformat(),
                'Контролируемые' if report.only_tracked else 'Все', m.planned, m.done, m.completed,
                m.partial, m.cancelled, m.moved, m.pending, m.completion_percent, m.planned_seconds / 60,
                m.actual_seconds / 60, m.unplanned_seconds / 60, m.unknown_seconds / 60,
                m.unplanned_percent, 'Да' if m.unknown_seconds else 'Нет', m.missing_time, m.comparable,
                m.mean_start_minutes, m.mean_duration_minutes, m.start_outside, m.duration_outside,
                m.overlap_seconds / 60, report.frozen_days if summary else None,
                report.loaded_days if summary else None, len(report.daily) if summary else None,
                report.source_warnings if summary else None]

    def value(v):
        return '' if v is None else f'{v:.2f}'.replace('.', ',') if isinstance(v, float) else v

    with Path(destination).open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream, delimiter=';')
        writer.writerow(headers)
        writer.writerow([value(v) for v in row('Итого', report.start, report.end, report.totals, True)])
        for day, metrics in report.daily.items():
            writer.writerow([value(v) for v in row('День', day, day + timedelta(days=1), metrics)])

