"""Compatibility is a precondition of startup, normal restore and emergency recovery."""
from contextlib import closing
from pathlib import Path
import sqlite3

import pytest

from director_control import __version__, backups, recovery, storage, updates
from director_control.storage import Store
from tests.test_local_events import old_database


def set_marker(path, value):
    with closing(sqlite3.connect(path)) as con:
        con.execute("INSERT OR REPLACE INTO settings VALUES ('app_last_version', ?)", (value,))
        con.commit()


def run_restore(mode, store, source):
    if mode == 'normal':
        return backups.restore_backup(store, source)
    return recovery.recover_database(store.path, source)


@pytest.mark.parametrize('mode', ['startup', 'normal', 'emergency'])
@pytest.mark.parametrize('marker', ['99.0.0', '0.99.0', '0.12.999', '', 'invalid', '0.12',
                                    'v0.12.0', '0.12.1rc1', b'0.12.0'])
def test_incompatible_marker_rejected_without_touching_originals(tmp_path, mode, marker):
    source = Store(tmp_path / 'source.db').path
    set_marker(source, marker)
    source_bytes = source.read_bytes()
    store = Store(tmp_path / 'live.db')
    if mode == 'emergency':
        store.path.write_bytes(b'damaged database')
    # Even sidecars must remain untouched when the source is rejected.
    for suffix in ('-wal', '-shm', '-journal'):
        Path(str(store.path) + suffix).write_bytes(b'original sidecar')
    before = {p: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
    with pytest.raises(ValueError) as error:
        if mode == 'startup':
            updates.prepare_version_update(source)
        else:
            run_restore(mode, store, source)
    if marker in ('99.0.0', '0.99.0', '0.12.999'):
        assert f'v{marker}' in str(error.value) and f'v{__version__}' in str(error.value)
    assert source.read_bytes() == source_bytes
    assert {p: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()} == before
    assert not (tmp_path / 'backups').exists()
    assert not (tmp_path / 'recovery').exists()


@pytest.mark.parametrize('mode', ['startup', 'normal', 'emergency'])
def test_newer_schema_rejected_even_with_current_app_marker(tmp_path, mode):
    source = Store(tmp_path / 'source.db').path
    set_marker(source, __version__)
    with closing(sqlite3.connect(source)) as con:
        con.execute('PRAGMA user_version=999')
    store = Store(tmp_path / 'live.db')
    before = store.path.read_bytes(), source.read_bytes()
    with pytest.raises(ValueError, match='новой'):
        if mode == 'startup':
            updates.prepare_version_update(source)
        else:
            run_restore(mode, store, source)
    assert (store.path.read_bytes(), source.read_bytes()) == before
    assert not (tmp_path / 'backups').exists()
    assert not (tmp_path / 'recovery').exists()


@pytest.mark.parametrize('mode', ['normal', 'emergency'])
@pytest.mark.parametrize('marker', [None, '0.9.0', '0.12.0', __version__])
def test_compatible_restore_survives_two_startups_with_plan_fact_and_history(tmp_path, mode, marker):
    original = Store(tmp_path / 'original.db')
    eid = original.create_event('Synthetic meeting', 'Работа', '2026-11-03T09:00:00', '2026-11-03T10:00:00')
    original.freeze_day('2026-11-03')
    original.update_event(eid, actual_start='2026-11-03T09:05:00', actual_end='2026-11-03T10:10:00',
                          status='done', note='Preserved note')
    original.set_setting('theme', 'dark')
    if marker is not None:
        set_marker(original.path, marker)
    source = backups.create_backup(original)
    before = source.read_bytes()
    expected_event, expected_rules = original.get_event(eid), original.baseline_rules()
    expected_audit = original.audit_log()
    store = Store(tmp_path / 'live.db')
    store.set_setting('theme', 'light')
    if mode == 'emergency':
        store.path.write_bytes(b'corrupt')
    run_restore(mode, store, source)
    # Exercise the actual startup ordering, rather than only constructing Store.
    updates.prepare_version_update(store.path)
    reopened = Store(store.path)
    updates.record_version(reopened)
    assert updates.prepare_version_update(store.path) is None
    reopened = Store(store.path)
    assert reopened.get_event(eid) == expected_event
    assert reopened.baseline_rules() == expected_rules
    assert reopened.is_frozen('2026-11-03')
    assert reopened.get_setting('theme') == 'dark'
    assert reopened.get_setting('app_last_version') == __version__
    assert all(row in reopened.audit_log() for row in expected_audit)
    assert any(row['action'] == 'Восстановление из копии' for row in reopened.audit_log())
    assert source.read_bytes() == before


@pytest.mark.parametrize('mode', ['normal', 'emergency'])
def test_legacy_schema_migrates_in_staging_and_passes_startup(tmp_path, mode):
    source = old_database(tmp_path / 'v2.db')
    before = source.read_bytes()
    store = Store(tmp_path / 'live.db')
    if mode == 'emergency':
        store.path.write_bytes(b'corrupt')
    run_restore(mode, store, source)
    updates.prepare_version_update(store.path)
    reopened = Store(store.path)
    updates.record_version(reopened)
    assert updates.prepare_version_update(store.path) is None
    assert backups.validate_database(store.path) == backups.SCHEMA_VERSION
    assert reopened.get_event(1).title == 'Реальная запись'
    assert reopened.baseline_rules()[1]['track'] == 1
    assert source.read_bytes() == before


@pytest.mark.parametrize('mode', ['normal', 'emergency'])
@pytest.mark.parametrize('phase', ['copy', 'migration'])
def test_staged_version_is_checked_before_migration_and_before_replacement(tmp_path, monkeypatch, mode, phase):
    source = Store(tmp_path / 'source.db').path
    store = Store(tmp_path / 'live.db')
    before = store.path.read_bytes()
    module = backups if mode == 'normal' else recovery
    copy_database = module._copy_database

    def changed_copy(src, dst):
        copy_database(src, dst)
        if Path(src) == source:
            set_marker(dst, '99.0.0')

    def staged_store(path):
        if phase == 'copy':
            pytest.fail('An incompatible staging file must never reach Store/migrations')
        staged = Store(path)
        staged.set_setting('app_last_version', '99.0.0')
        return staged

    if phase == 'copy':
        monkeypatch.setattr(module, '_copy_database', changed_copy)
    monkeypatch.setattr(storage, 'Store', staged_store)
    with pytest.raises(ValueError, match='новой'):
        run_restore(mode, store, source)
    assert store.path.read_bytes() == before
    assert not (tmp_path / 'recovery').exists()
    assert not list(tmp_path.glob('.director-snapshot-*'))
    assert not list(tmp_path.glob('.recovery-*'))


def test_rejected_restore_keeps_gui_open_and_reports_required_version(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    from tests.test_backup_ui import make_window, settle

    app, store, eid, window = make_window(tmp_path)
    source = Store(tmp_path / 'future.db').path
    set_marker(source, '99.0.0')
    before = store.path.read_bytes()
    warnings = []
    restored = []
    window.backup_panel.restored.connect(restored.append)
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *args: (str(source), ''))
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: warnings.append(args[2]))
    window.show()
    try:
        window.backup_panel.restore_button.click()
        settle(app, window.backup_panel)
        assert window.isEnabled() and window.isVisible()
        assert not restored
        assert warnings and 'v99.0.0' in warnings[0]
        assert store.path.read_bytes() == before
        assert store.get_event(eid).title == 'Исходное событие'
    finally:
        window.close()
