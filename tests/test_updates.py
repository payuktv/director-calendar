from pathlib import Path
import sqlite3

import pytest

from director_control import updates
from director_control.storage import Store


def database(tmp_path):
    store = Store(tmp_path / 'director_control.db')
    eid = store.create_event('Проверка', 'Работа', '2026-10-29T09:00:00', '2026-10-29T10:00:00',
                             actual_start='2026-10-29T09:05:00', actual_end='2026-10-29T10:05:00', status='done')
    store.freeze_day('2026-10-29')
    store.set_setting('theme', 'dark')
    store.set_setting('mail_login', 'synthetic@example.test')
    return store, eid


def test_update_backup_precedes_any_live_write_and_preserves_all_tables(tmp_path):
    store, eid = database(tmp_path)
    before = store.path.read_bytes()
    copy = updates.prepare_version_update(store.path)
    assert copy and copy.is_file() and store.path.read_bytes() == before
    with sqlite3.connect(store.path) as live, sqlite3.connect(copy) as backup:
        assert list(live.iterdump()) == list(backup.iterdump())
    updates.record_version(store)
    assert store.get_event(eid).status == 'done'
    assert store.get_setting('theme') == 'dark'
    assert updates.prepare_version_update(store.path) is None
    assert len(list(copy.parent.glob('before-update-*.db'))) == 1


def test_new_install_needs_no_backup(tmp_path):
    path = tmp_path / 'new.db'
    assert updates.prepare_version_update(path) is None
    assert not path.exists()


def test_backup_failure_stops_update_without_modifying_database(tmp_path, monkeypatch):
    store, _ = database(tmp_path)
    before = store.path.read_bytes()
    def fail(*a, **kw):
        raise OSError('Disk full')
    monkeypatch.setattr(updates, 'create_backup', fail)
    with pytest.raises(OSError):
        updates.prepare_version_update(store.path)
    assert before == store.path.read_bytes()
    assert not store.get_setting('app_last_version')


def test_newer_or_invalid_version_rejected_without_writes(tmp_path):
    store, _ = database(tmp_path)
    for version in ('9.0.0', 'invalid'):
        store.set_setting('app_last_version', version)
        before = store.path.read_bytes()
        with pytest.raises(ValueError):
            updates.prepare_version_update(store.path)
        assert before == store.path.read_bytes()


def test_corrupt_database_is_not_replaced(tmp_path):
    path = tmp_path / 'broken.db'
    path.write_bytes(b'not a database')
    with pytest.raises(ValueError):
        updates.prepare_version_update(path)
    assert path.read_bytes() == b'not a database'


def test_each_new_version_gets_its_own_backup(tmp_path):
    store, _ = database(tmp_path)
    updates.record_version(store, '0.10.0')
    first = updates.prepare_version_update(store.path, '0.11.0')
    updates.record_version(store, '0.11.0')
    second = updates.prepare_version_update(store.path, '0.12.0')
    assert first != second and Path(first).is_file() and Path(second).is_file()
