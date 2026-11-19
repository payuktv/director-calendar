"""Allow only application-owned SQLite schemas before inspecting imported data.

DDL is compared as tokens, never executed from a backup. Ordinary legacy indexes
may reference real columns; expressions, partial indexes, views and triggers may
not introduce executable SQL. Keep historical table variants when schema evolves.
"""
from pathlib import Path
import re
import sqlite3
from time import monotonic

from .i18n import tr

MAX_DATABASE_BYTES = 512 * 1024 * 1024
MAX_VALUE_BYTES = 8 * 1024 * 1024
MAX_SCHEMA_OBJECTS = 64
VALIDATION_SECONDS = 15
COPY_SECONDS = 30
SCHEMA_ERROR = 'Схема копии не соответствует Director Calendar. Выбери исходную копию приложения.'


class Budget:
    def __init__(self, seconds):
        self.deadline = monotonic() + seconds

    def expired(self):
        return monotonic() >= self.deadline

    def check(self):
        if self.expired():
            raise ValueError(tr('Проверка или копирование базы превысили допустимое время.'))


def check_file_size(path):
    # Include WAL input: the main file alone need not contain all committed data.
    total = 0
    for suffix in ('', '-wal', '-journal'):
        candidate = Path(str(path) + suffix)
        if candidate.exists():
            total += candidate.stat().st_size
    if total > MAX_DATABASE_BYTES:
        raise ValueError(tr('Размер базы превышает допустимые 512 МиБ.'))


def configure_connection(con, *, inspection=False):
    con.setconfig(sqlite3.SQLITE_DBCONFIG_DEFENSIVE, True)
    con.setconfig(sqlite3.SQLITE_DBCONFIG_TRUSTED_SCHEMA, False)
    if inspection:
        con.setconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_TRIGGER, False)
        con.setconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_VIEW, False)
        for limit, value in ((sqlite3.SQLITE_LIMIT_LENGTH, MAX_VALUE_BYTES),
                             (sqlite3.SQLITE_LIMIT_SQL_LENGTH, 128 * 1024),
                             (sqlite3.SQLITE_LIMIT_COLUMN, 64),
                             (sqlite3.SQLITE_LIMIT_EXPR_DEPTH, 30),
                             (sqlite3.SQLITE_LIMIT_ATTACHED, 0)):
            con.setlimit(limit, value)
        con.execute('PRAGMA query_only=ON')
        con.execute('PRAGMA cell_size_check=ON')
        con.execute('PRAGMA mmap_size=0')
        con.execute('PRAGMA cache_size=-2048')


_TOKEN = re.compile(r"\s+|'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"|[A-Za-z_][A-Za-z_0-9]*|[0-9]+|[(),;]")


def tokens(sql):
    result, position = [], 0
    if not isinstance(sql, str) or len(sql) > 128 * 1024:
        raise ValueError(tr(SCHEMA_ERROR))
    for match in _TOKEN.finditer(sql):
        if match.start() != position:
            raise ValueError(tr(SCHEMA_ERROR))
        position = match.end()
        token = match[0]
        if token.isspace():
            continue
        if token.startswith('"'):
            token = token[1:-1].replace('""', '"').lower()
        elif not token.startswith("'"):
            token = token.lower()
        result.append(token)
    if position != len(sql):
        raise ValueError(tr(SCHEMA_ERROR))
    if result and result[-1] == ';':
        result.pop()
    return tuple(result)


# Populated with canonical, application-owned DDL below.
TABLE_SQL = {
    "categories": "CREATE TABLE categories ( name TEXT PRIMARY KEY, color TEXT NOT NULL, track INTEGER NOT NULL DEFAULT 1 )",
    "events": "CREATE TABLE events ( id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, category TEXT NOT NULL REFERENCES categories(name), current_start TEXT, current_end TEXT, baseline_start TEXT, baseline_end TEXT, actual_start TEXT, actual_end TEXT, status TEXT NOT NULL DEFAULT 'pending', note TEXT NOT NULL DEFAULT '', source TEXT NOT NULL DEFAULT 'manual', external_key TEXT UNIQUE, created_at TEXT NOT NULL, updated_at TEXT NOT NULL )",
    "day_freezes": "CREATE TABLE day_freezes ( day TEXT PRIMARY KEY, frozen_at TEXT NOT NULL )",
    "audit": "CREATE TABLE audit ( id INTEGER PRIMARY KEY AUTOINCREMENT, event_id INTEGER, title TEXT NOT NULL, action TEXT NOT NULL, details TEXT NOT NULL, changed_at TEXT NOT NULL )",
    "settings": "CREATE TABLE settings ( key TEXT PRIMARY KEY, value TEXT NOT NULL )",
    "calendar_events": "CREATE TABLE calendar_events ( event_id INTEGER PRIMARY KEY REFERENCES events(id) ON DELETE CASCADE, calendar_key TEXT NOT NULL, uid TEXT NOT NULL, recurrence_id TEXT NOT NULL, missing INTEGER NOT NULL DEFAULT 0, cancelled INTEGER NOT NULL DEFAULT 0, all_day INTEGER NOT NULL DEFAULT 0, baseline_all_day INTEGER, local_status INTEGER NOT NULL DEFAULT 0 )",
    "baseline_rules": "CREATE TABLE baseline_rules ( event_id INTEGER PRIMARY KEY REFERENCES events(id) ON DELETE CASCADE, category TEXT NOT NULL, track INTEGER NOT NULL CHECK(track IN (0,1)), tolerance_minutes INTEGER NOT NULL)",
    "calendar_syncs": "CREATE TABLE calendar_syncs ( id INTEGER PRIMARY KEY AUTOINCREMENT, calendar_key TEXT NOT NULL, start TEXT NOT NULL, end TEXT NOT NULL, status TEXT NOT NULL, finished_at TEXT NOT NULL)",
    "sqlite_sequence": "CREATE TABLE sqlite_sequence(name,seq)"
}


def _table_variants():
    variants = {name: {tokens(sql)} for name, sql in TABLE_SQL.items()}
    event_sql = TABLE_SQL['events']
    for nullable in (True, False):
        sql = event_sql
        if not nullable:
            sql = sql.replace('current_start TEXT', 'current_start TEXT NOT NULL')
            sql = sql.replace('current_end TEXT', 'current_end TEXT NOT NULL')
        variants['events'].add(tokens(sql))
        variants['events'].add(tokens(sql.rstrip()[:-1] + ', revision INTEGER NOT NULL DEFAULT 0)'))
    return variants


def validate_schema(con):
    known = _table_variants()
    rows = con.execute('SELECT type,name,tbl_name,sql FROM sqlite_schema').fetchmany(MAX_SCHEMA_OBJECTS + 1)
    if len(rows) > MAX_SCHEMA_OBJECTS:
        raise ValueError(tr(SCHEMA_ERROR))
    tables = set()
    for kind, name, table, sql in rows:
        if kind == 'table':
            if name != table or name not in known or tokens(sql) not in known[name]:
                raise ValueError(tr(SCHEMA_ERROR))
            tables.add(name)
        elif kind != 'index':
            raise ValueError(tr(SCHEMA_ERROR))
    # Index column names are read only after the table DDL has been approved.
    columns = {name: {r[1].lower() for r in con.execute('PRAGMA table_info("' + name + '")')}
               for name in tables}
    for kind, name, table, sql in rows:
        if kind != 'index':
            continue
        if table not in tables:
            raise ValueError(tr(SCHEMA_ERROR))
        if sql is None:
            if not re.fullmatch('sqlite_autoindex_' + re.escape(table) + r'_[1-9][0-9]*', name):
                raise ValueError(tr(SCHEMA_ERROR))
            continue
        parts = tokens(sql)
        if parts[:6] != ('create', 'index', name.lower(), 'on', table.lower(), '(') or parts[-1:] != (')',):
            raise ValueError(tr(SCHEMA_ERROR))
        inner = list(parts[6:-1])
        while inner:
            if inner.pop(0) not in columns[table]:
                raise ValueError(tr(SCHEMA_ERROR))
            if inner and inner[0] in ('asc', 'desc'):
                inner.pop(0)
            if inner and (inner.pop(0) != ',' or not inner):
                raise ValueError(tr(SCHEMA_ERROR))
        if len(parts) < 8:
            raise ValueError(tr(SCHEMA_ERROR))
