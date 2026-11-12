"""Read-only validation of application records, including SQLite storage types.

An approved SQL schema is not enough: SQLite affinity still permits BLOBs in
TEXT columns and strings in INTEGER columns. Keep this gate independent of Qt
and migrations so every restore/startup can reject a copy before any writes.
"""
from datetime import date, datetime
import json
import math


ERROR = 'В базе некорректные записи приложения. Выбери другую резервную копию.'
MAX_JSON_DEPTH = 32
MAX_JSON_NODES = 100000
MAX_INTEGER = 2**63 - 2  # Leave room for incrementing a revision/sequence.


def _require(condition):
    if not condition:
        raise ValueError(ERROR)


def _text(value, *, nullable=False, nonempty=False, maximum=None):
    if nullable and value is None:
        return
    _require(isinstance(value, str) and '\0' not in value)
    _require(not nonempty or bool(value.strip()))
    _require(maximum is None or len(value) <= maximum)


def _integer(value, low=0, high=MAX_INTEGER, *, nullable=False):
    if nullable and value is None:
        return
    _require(type(value) is int and low <= value <= high)


def _timestamp(value, *, local=False):
    _text(value, nonempty=True, maximum=64)
    stamp = datetime.fromisoformat(value)
    # Application queries use an ISO date prefix; compact/week-date forms are
    # accepted by fromisoformat but are not compatible with those queries.
    _require(value[:10] == stamp.date().isoformat())
    _require(not local or stamp.tzinfo is None)
    _require(not local or (len(value) > 10 and value[10] == 'T'))
    return stamp


def _interval(start, end):
    if start is None and end is None:
        return
    _require(start is not None and end is not None)
    _require(_timestamp(start, local=True) < _timestamp(end, local=True))


def _history_details(raw, budget):
    _text(raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Historical plain-text descriptions are deliberately supported by the
        # history viewer. They are not executed or interpreted as application state.
        return
    # Bound nested JSON before the history formatter recursively visits it.
    # Use an iterator stack rather than copying all children of a large object.
    stack = [(iter((data,)), 0)]
    nodes = 0
    while stack:
        items, depth = stack[-1]
        try:
            value = next(items)
        except StopIteration:
            stack.pop()
            continue
        nodes += 1
        _require(nodes <= MAX_JSON_NODES and depth <= MAX_JSON_DEPTH)
        if nodes % 256 == 0:
            budget.check()
        if isinstance(value, dict):
            for key in value:
                _text(key)
            stack.append((iter(value.values()), depth + 1))
        elif isinstance(value, list):
            stack.append((iter(value), depth + 1))
        elif isinstance(value, str):
            _text(value)
        elif isinstance(value, float):
            _require(math.isfinite(value))


def _rows(con, table, budget):
    # table is selected exclusively from the fixed names below, after the DDL
    # allowlist has passed. No database-provided identifier enters this SQL.
    cursor = con.execute('SELECT * FROM "' + table + '"')
    names = [column[0] for column in cursor.description]
    for values in cursor:
        budget.check()
        yield dict(zip(names, values))


def validate_records(con, tables, budget):
    try:
        for row in _rows(con, 'categories', budget):
            _text(row['name'], nonempty=True, maximum=60)
            _text(row['color'], nonempty=True, maximum=128)
            _integer(row['track'], 0, 1)
        for row in _rows(con, 'events', budget):
            _integer(row['id'], 1)
            _text(row['title'], nonempty=True, maximum=200)
            _text(row['category'], nonempty=True, maximum=60)
            _text(row['note'])
            _text(row['external_key'], nullable=True)
            for field in ('created_at', 'updated_at'):
                _timestamp(row[field])
            for layer in ('current', 'baseline', 'actual'):
                _interval(row[layer + '_start'], row[layer + '_end'])
            _require(row['status'] in ('pending', 'done', 'partial', 'cancelled', 'moved'))
            _require(row['source'] in ('local', 'caldav', 'manual'))
            if 'revision' in row:
                _integer(row['revision'])
        for row in _rows(con, 'day_freezes', budget):
            _text(row['day'], maximum=10)
            _require(date.fromisoformat(row['day']).isoformat() == row['day'])
            _timestamp(row['frozen_at'])
        for row in _rows(con, 'audit', budget):
            _integer(row['id'], 1)
            # Deleted events deliberately keep their history; this is not an FK.
            _integer(row['event_id'], 1, nullable=True)
            _text(row['title'])
            _text(row['action'], nonempty=True)
            _timestamp(row['changed_at'])
            _history_details(row['details'], budget)
        if 'calendar_events' in tables:
            for row in _rows(con, 'calendar_events', budget):
                _integer(row['event_id'], 1)
                _text(row['calendar_key'], nonempty=True)
                _text(row['uid'], nonempty=True)
                # An empty recurrence ID is valid in older application copies.
                _text(row['recurrence_id'])
                for field in ('missing', 'cancelled', 'all_day', 'local_status'):
                    _integer(row[field], 0, 1)
                _integer(row['baseline_all_day'], 0, 1, nullable=True)
        if 'baseline_rules' in tables:
            for row in _rows(con, 'baseline_rules', budget):
                _integer(row['event_id'], 1)
                _text(row['category'], nonempty=True, maximum=60)
                _integer(row['track'], 0, 1)
                _integer(row['tolerance_minutes'], 0, 180)
        if 'calendar_syncs' in tables:
            for row in _rows(con, 'calendar_syncs', budget):
                _integer(row['id'], 1)
                _text(row['calendar_key'], nonempty=True)
                _require(row['start'] is not None and row['end'] is not None)
                _interval(row['start'], row['end'])
                _require(row['status'] in ('complete', 'partial', 'failed'))
                _timestamp(row['finished_at'], local=True)
        if 'sqlite_sequence' in tables:
            seen = set()
            for row in _rows(con, 'sqlite_sequence', budget):
                _text(row['name'])
                _require(row['name'] in {'events', 'audit', 'calendar_syncs'} and row['name'] not in seen)
                seen.add(row['name'])
                _integer(row['seq'])
    except (ValueError, TypeError, OverflowError, RecursionError):
        budget.check()
        # Never include event text, account identifiers or raw JSON in an error.
        raise ValueError(ERROR) from None
    budget.check()
