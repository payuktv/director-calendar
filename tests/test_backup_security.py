"""Untrusted backups must not execute SQL or replace any working data."""
from contextlib import closing
from pathlib import Path
import sqlite3

import pytest

from director_control import backups, database_guard as guard, recovery, updates
from director_control.storage import Store


def poison(path, kind):
    with closing(sqlite3.connect(path)) as con:
        if kind == 'trigger':
            con.execute('CREATE TRIGGER erase AFTER INSERT ON audit BEGIN DELETE FROM events; END')
        elif kind == 'fts-trigger':
            con.execute('CREATE VIRTUAL TABLE injected_fts USING fts5(content)')
            con.execute("INSERT INTO injected_fts VALUES ('synthetic')")
            con.execute("""CREATE TRIGGER fts_query AFTER INSERT ON audit BEGIN
                INSERT OR REPLACE INTO settings VALUES ('untrusted_sql_ran',
                    (SELECT count(*) FROM injected_fts WHERE injected_fts MATCH 'synthetic')); END""")
        elif kind == 'virtual-table':
            con.execute('CREATE VIRTUAL TABLE injected_fts USING fts5(content)')
        elif kind == 'view':
            con.execute('CREATE VIEW injected AS SELECT * FROM events')
        elif kind == 'generated-column':
            con.execute('ALTER TABLE events ADD COLUMN injected TEXT GENERATED ALWAYS AS (upper(title)) VIRTUAL')
        elif kind == 'expression-index':
            con.execute('CREATE INDEX injected ON events(length(title))')
        elif kind == 'partial-index':
            con.execute("CREATE INDEX injected ON events(title) WHERE title <> ''")
        elif kind == 'table-default':
            con.execute('PRAGMA writable_schema=ON')
            con.execute("UPDATE sqlite_master SET sql=replace(sql,\"DEFAULT 'pending'\",\"DEFAULT (hex(randomblob(50000000)))\") WHERE name='events'")
        else:
            raise AssertionError(kind)
        con.commit()


@pytest.mark.parametrize('mode', ['normal', 'emergency', 'startup'])
@pytest.mark.parametrize('kind', ['trigger', 'fts-trigger', 'virtual-table', 'view', 'generated-column',
                                 'expression-index', 'partial-index', 'table-default'])
def test_foreign_schema_is_rejected_before_any_write(tmp_path, mode, kind):
    original = Store(tmp_path / 'source.db')
    original.create_event('Synthetic', 'Работа', '2026-11-06T09:00:00', '2026-11-06T10:00:00')
    poison(original.path, kind)
    store = Store(tmp_path / 'live.db')
    if mode == 'emergency':
        store.path.write_bytes(b'original damaged database')
        Path(str(store.path) + '-wal').write_bytes(b'original journal')
    before = {p: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
    with pytest.raises(ValueError):
        if mode == 'normal':
            backups.restore_backup(store, original.path)
        elif mode == 'emergency':
            recovery.recover_database(store.path, original.path)
        else:
            updates.prepare_version_update(original.path)
    assert {p: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()} == before
    assert not (tmp_path / 'backups').exists()
    assert not (tmp_path / 'recovery').exists()


@pytest.mark.parametrize('mode', ['normal', 'emergency'])
def test_staging_is_rechecked_before_opening_store(tmp_path, monkeypatch, mode):
    source = Store(tmp_path / 'source.db').path
    store = Store(tmp_path / 'live.db')
    before = store.path.read_bytes()
    module = backups if mode == 'normal' else recovery
    copy = module._copy_database
    def changed_copy(src, dst):
        copy(src, dst)
        if Path(src) == source:
            poison(dst, 'trigger')
    monkeypatch.setattr(module, '_copy_database', changed_copy)
    with pytest.raises(ValueError):
        if mode == 'normal':
            backups.restore_backup(store, source)
        else:
            recovery.recover_database(store.path, source)
    assert store.path.read_bytes() == before
    assert not list(tmp_path.glob('.director-snapshot-*'))
    assert not list(tmp_path.glob('.recovery-*'))


def test_oversized_backup_is_rejected_without_opening_sqlite(tmp_path, monkeypatch):
    source = Store(tmp_path / 'source.db').path
    monkeypatch.setattr(guard, 'MAX_DATABASE_BYTES', source.stat().st_size - 1)
    def forbidden(*args, **kwargs):
        pytest.fail('Oversized input must not reach SQLite')
    monkeypatch.setattr(sqlite3, 'connect', forbidden)
    with pytest.raises(ValueError, match='512'):
        backups.validate_database(source)


@pytest.mark.parametrize('phase', ['validate', 'copy'])
def test_expired_budget_aborts_without_replacing_the_working_database(tmp_path, monkeypatch, phase):
    source = Store(tmp_path / 'source.db').path
    store = Store(tmp_path / 'live.db')
    before = store.path.read_bytes()
    monkeypatch.setattr(guard, 'VALIDATION_SECONDS' if phase == 'validate' else 'COPY_SECONDS', 0)
    with pytest.raises(ValueError, match='время'):
        backups.restore_backup(store, source)
    assert store.path.read_bytes() == before
    assert not list(tmp_path.rglob('.director-snapshot-*'))


def test_sql_vm_progress_and_value_limits_are_active(tmp_path):
    source = Store(tmp_path / 'source.db').path
    budget = guard.Budget(100)
    with closing(backups._read_only(source, budget)) as con:
        assert not con.getconfig(sqlite3.SQLITE_DBCONFIG_TRUSTED_SCHEMA)
        assert not con.getconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_TRIGGER)
        assert not con.getconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_VIEW)
        assert con.getconfig(sqlite3.SQLITE_DBCONFIG_DEFENSIVE)
        assert con.getlimit(sqlite3.SQLITE_LIMIT_LENGTH) == guard.MAX_VALUE_BYTES
        budget.deadline = 0
        with pytest.raises(sqlite3.OperationalError, match='interrupted'):
            con.execute('WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n WHERE x<1000000) SELECT sum(x) FROM n').fetchone()
