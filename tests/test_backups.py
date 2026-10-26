from datetime import datetime, timedelta
from pathlib import Path
import sqlite3

import pytest

from director_control import backups
from director_control.storage import Store
from tests.test_local_events import old_database


def event(store):
    return store.create_event('Встреча', 'Работа', '2026-10-26T09:00:00', '2026-10-26T10:00:00')


def test_daily_copies_are_verified_rotated_and_do_not_remove_manual_files(tmp_path):
    store = Store(tmp_path / 'live.db')
    eid = event(store)
    folder = tmp_path / 'Архив копий'
    backups.save_backup_settings(store, True, str(folder), 2)
    manual = backups.create_backup(store, folder)
    unrelated = folder / 'auto-other-database-20261026-090000-000000.db'
    unrelated.write_text('do not delete')
    now = datetime(2026, 10, 26, 10)
    first = backups.scheduled_backup(store, now)
    assert backups.validate_database(first) == 4
    assert backups.scheduled_backup(store, now+timedelta(hours=1)) is None
    second = backups.scheduled_backup(store, now+timedelta(days=1))
    third = backups.scheduled_backup(store, now+timedelta(days=2))
    assert not first.exists() and second.exists() and third.exists()
    assert manual.exists() and unrelated.read_text() == 'do not delete'
    with sqlite3.connect(third) as con:
        assert con.execute('SELECT title FROM events WHERE id=?', (eid,)).fetchone()[0] == 'Встреча'
    backups.save_backup_settings(store, False, str(folder), 2)
    assert backups.scheduled_backup(store, now+timedelta(days=3)) is None


def test_changing_backup_folder_or_removing_last_copy_creates_a_new_daily_copy(tmp_path):
    store = Store(tmp_path / 'live.db')
    now = datetime(2026, 10, 26, 10)
    first = backups.scheduled_backup(store, now)
    first.unlink()
    assert backups.scheduled_backup(store, now).is_file()
    backups.save_backup_settings(store, True, str(tmp_path / 'new-folder'), 30)
    assert backups.scheduled_backup(store, now).parent == tmp_path / 'new-folder'


def test_failed_copy_does_not_record_success_or_leave_a_partial_snapshot(tmp_path, monkeypatch):
    store = Store(tmp_path / 'live.db')
    eid = event(store)
    def fail(source, target):
        Path(target).write_bytes(b'partial')
        raise OSError('Диск недоступен')
    monkeypatch.setattr(backups, '_copy_database', fail)
    with pytest.raises(OSError):
        backups.scheduled_backup(store)
    assert store.get_setting('backup_last_auto') == ''
    assert list((tmp_path / 'backups').iterdir()) == []
    assert store.get_event(eid).title == 'Встреча'


def test_restore_preserves_the_old_live_database_and_restores_rules_and_history(tmp_path):
    store = Store(tmp_path / 'live.db')
    eid = event(store)
    store.freeze_day('2026-10-26')
    store.set_setting('ui_theme', 'dark')
    original = backups.create_backup(store)
    original_bytes = original.read_bytes()
    store.update_event(eid, title='После копирования', status='done')
    store.set_setting('ui_theme', 'light')
    safety = backups.restore_backup(store, original)
    restored = Store(store.path)
    assert restored.get_event(eid).title == 'Встреча' and restored.get_event(eid).status == 'pending'
    assert restored.get_setting('ui_theme') == 'dark'
    assert restored.baseline_rules()[eid]['category'] == 'Работа'
    assert restored.is_frozen('2026-10-26')
    assert restored.audit_log()[0]['action'] == 'Восстановление из копии'
    with sqlite3.connect(safety) as con:
        assert con.execute('SELECT title FROM events WHERE id=?', (eid,)).fetchone()[0] == 'После копирования'
    assert original.read_bytes() == original_bytes


def test_restore_old_v2_copy_upgrades_staging_before_replacing_live_data(tmp_path):
    store = Store(tmp_path / 'live.db')
    event(store)
    source = old_database(tmp_path / 'v2.db')
    assert backups.validate_database(source) == 2
    backups.restore_backup(store, source)
    restored = Store(store.path)
    assert backups.validate_database(store.path) == 4
    assert restored.get_event(1).title == 'Реальная запись'
    assert restored.get_event(1).baseline_start
    assert restored.baseline_rules()[1]['track'] == 1
    assert event(restored) > 50


@pytest.mark.parametrize('kind', ['corrupt', 'foreign', 'newer', 'missing-field', 'orphan'])
def test_invalid_backup_never_replaces_live_data(tmp_path, kind):
    store = Store(tmp_path / 'live.db')
    eid = event(store)
    source = tmp_path / 'bad.db'
    if kind == 'corrupt':
        source.write_bytes(b'not sqlite')
    elif kind == 'foreign':
        with sqlite3.connect(source) as con:
            con.execute('CREATE TABLE unrelated (value TEXT)')
    else:
        source = backups.create_backup(store)
        with sqlite3.connect(source) as con:
            if kind == 'newer':
                con.execute('PRAGMA user_version=999')
            elif kind == 'missing-field':
                con.execute('ALTER TABLE events RENAME COLUMN revision TO lost_revision')
            else:
                con.execute("INSERT INTO calendar_events(event_id,calendar_key,uid,recurrence_id) VALUES (999,'key','uid','')")
    before = store.path.read_bytes()
    with pytest.raises(ValueError):
        backups.restore_backup(store, source)
    assert store.path.read_bytes() == before and store.get_event(eid).title == 'Встреча'


def test_failed_final_restore_swap_keeps_working_data_and_safety_copy(tmp_path, monkeypatch):
    store = Store(tmp_path / 'live.db')
    eid = event(store)
    source = backups.create_backup(store)
    store.update_event(eid, title='Текущая версия')
    replace = backups.os.replace
    def fail_final(src, dst):
        if Path(dst) == store.path:
            raise OSError('Cannot replace working database')
        return replace(src, dst)
    monkeypatch.setattr(backups.os, 'replace', fail_final)
    with pytest.raises(OSError):
        backups.restore_backup(store, source)
    assert store.get_event(eid).title == 'Текущая версия'
    assert list((tmp_path / 'backups').glob('before-restore-*.db'))
    assert not list(tmp_path.glob('.director-snapshot-*.db'))


def test_wal_pages_are_included_in_backup_and_active_connections_block_restore(tmp_path):
    store = Store(tmp_path / 'wal.db')
    eid = event(store)
    keeper = sqlite3.connect(store.path)
    try:
        assert keeper.execute('PRAGMA journal_mode=WAL').fetchone()[0] == 'wal'
        store.update_event(eid, title='Событие из WAL')
        source = backups.create_backup(store)
        with sqlite3.connect(source) as con:
            assert con.execute('SELECT title FROM events WHERE id=?', (eid,)).fetchone()[0] == 'Событие из WAL'
        store.update_event(eid, title='Текущая версия')
        keeper.execute('BEGIN')
        assert keeper.execute('SELECT title FROM events WHERE id=?', (eid,)).fetchone()[0] == 'Текущая версия'
        with pytest.raises(ValueError, match='занята'):
            backups.restore_backup(store, source)
        assert store.get_event(eid).title == 'Текущая версия'
    finally:
        keeper.rollback()
        keeper.close()
    backups.restore_backup(store, source)
    assert Store(store.path).get_event(eid).title == 'Событие из WAL'
    assert not list(tmp_path.rglob('.director-snapshot-*'))


def test_schema4_migration_failure_rolls_back_added_columns_and_keeps_v3_copy(tmp_path):
    from tests.test_local_events import V2_SCHEMA, START, END
    path = tmp_path / 'v3.db'
    with sqlite3.connect(path) as con:
        con.executescript(V2_SCHEMA.replace('TEXT NOT NULL', 'TEXT').replace('user_version=2', 'user_version=3'))
        con.execute("INSERT INTO categories VALUES ('Работа','#123456',1)")
        con.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (1, 'Событие', 'Работа', START, END, START, END, None, None, 'pending', '', 'local', None, START, START))
        con.executescript('''CREATE TABLE baseline_rules (event_id INTEGER PRIMARY KEY REFERENCES events(id),category TEXT,track INTEGER,tolerance_minutes INTEGER);
            CREATE TRIGGER migration_failure BEFORE INSERT ON baseline_rules BEGIN SELECT RAISE(ABORT,'simulated storage failure'); END;''')
    with pytest.raises(sqlite3.IntegrityError, match='simulated storage failure'):
        Store(path)
    with sqlite3.connect(path) as con:
        assert con.execute('PRAGMA user_version').fetchone()[0] == 3
        assert 'revision' not in {row[1] for row in con.execute('PRAGMA table_info(events)')}
        assert con.execute('SELECT title FROM events').fetchone()[0] == 'Событие'
    saved = next((tmp_path / 'backups').glob('backup-*.db'))
    assert backups.validate_database(saved) == 3
