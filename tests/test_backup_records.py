"""Reject structurally valid SQLite copies whose records cannot be used safely."""
from contextlib import closing
from datetime import date
import json
from pathlib import Path
import sqlite3

import pytest

from director_control import __version__, backups, recovery, storage, updates
from director_control.storage import Store
from tests.test_backup_settings import dispose_window
from tests.test_mail_only import imported_snapshot

DAY = '2026-10-22'
BAD_RECORDS = [
    ('categories', 'name', b'private-value'), ('categories', 'name', None),
    ('categories', 'name', 'x' * 61), ('categories', 'color', b'#123456'),
    ('categories', 'track', 'invalid'), ('categories', 'track', 2),
    ('events', 'title', b'private-value'), ('events', 'title', ''),
    ('events', 'note', b'private-value'), ('events', 'note', 'private\0value'),
    ('events', 'external_key', b'private-value'),
    ('events', 'created_at', 'invalid'), ('events', 'updated_at', b'private-value'),
    ('events', 'revision', 'invalid'), ('events', 'revision', -1),
    ('events', 'revision', 1.5), ('events', 'current_start', b'2026-10-22T09:00:00'),
    ('events', 'current_start', '20261022T09:00:00'),
    ('events', 'current_start', '2026-10-22 09:00:00'),
    ('events', 'actual_end', '2026-10-22T11:00:00+03:00'),
    ('day_freezes', 'day', '2026-02-30'), ('day_freezes', 'frozen_at', b'private-value'),
    ('audit', 'title', b'private-value'), ('audit', 'event_id', 'invalid'),
    ('audit', 'action', b'private-value'), ('audit', 'details', b'private-value'),
    ('audit', 'details', '[' * 40 + '0' + ']' * 40),
    ('audit', 'details', '[' * 1100 + '0' + ']' * 1100),
    ('audit', 'details', '{"value":NaN}'), ('audit', 'changed_at', 'invalid'),
    ('calendar_events', 'calendar_key', b'private-value'),
    ('calendar_events', 'uid', b'private-value'),
    ('calendar_events', 'recurrence_id', b'private-value'),
    ('calendar_events', 'missing', 2), ('calendar_events', 'all_day', 'invalid'),
    ('calendar_events', 'cancelled', 0.5), ('calendar_events', 'baseline_all_day', 2),
    ('calendar_events', 'local_status', -1),
    ('baseline_rules', 'category', b'private-value'),
    ('baseline_rules', 'tolerance_minutes', 'invalid'),
    ('baseline_rules', 'tolerance_minutes', b'10'),
    ('baseline_rules', 'tolerance_minutes', -1),
    ('baseline_rules', 'tolerance_minutes', 181),
    ('baseline_rules', 'tolerance_minutes', 10.5),
    ('calendar_syncs', 'start', b'private-value'),
    ('calendar_syncs', 'end', '1900-01-01T00:00:00'),
    ('calendar_syncs', 'status', 'unknown'),
    ('calendar_syncs', 'finished_at', '2026-10-22T09:00:00Z'),
    ('sqlite_sequence', 'name', b'private-value'), ('sqlite_sequence', 'seq', 'invalid'),
]


def populated(path):
    store = Store(path)
    store.set_setting('app_last_version', __version__)
    store.set_setting('mail_auto', '0')
    store.set_setting('backup_auto', '0')
    store.add_category('Extra')
    eid = store.create_event('Synthetic local', 'Работа', DAY + 'T11:00:00', DAY + 'T12:00:00',
                             actual_start=DAY + 'T11:05:00', actual_end=DAY + 'T12:05:00', status='done')
    store.apply_calendar_snapshot(imported_snapshot())
    store.freeze_day(DAY)
    return store, eid


def change(path, table, field, value):
    with closing(sqlite3.connect(path)) as con:
        # Identifiers are test constants, never input from a backup.
        where = "name='Extra'" if table == 'categories' else f'rowid=(SELECT min(rowid) FROM {table})'
        con.execute(f'UPDATE {table} SET {field}=? WHERE {where}', (value,))
        con.commit()


@pytest.mark.parametrize('mode', ['normal', 'emergency', 'startup'])
@pytest.mark.parametrize('table,field,value', BAD_RECORDS)
def test_invalid_records_rejected_before_any_file_changes(tmp_path, mode, table, field, value):
    source, _ = populated(tmp_path / 'source.db')
    change(source.path, table, field, value)
    live = Store(tmp_path / 'live.db')
    if mode == 'emergency':
        live.path.write_bytes(b'original damaged database')
        Path(str(live.path) + '-wal').write_bytes(b'original journal')
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    with pytest.raises(ValueError) as error:
        if mode == 'startup':
            updates.prepare_version_update(source.path)
        elif mode == 'normal':
            backups.restore_backup(live, source.path)
        else:
            recovery.recover_database(live.path, source.path)
    assert 'private' not in str(error.value)
    assert {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()} == before


@pytest.mark.parametrize('mode', ['normal', 'emergency'])
@pytest.mark.parametrize('phase', ['copy', 'migration'])
def test_invalid_staging_records_never_replace_the_working_database(tmp_path, monkeypatch, mode, phase):
    source, _ = populated(tmp_path / 'source.db')
    live = Store(tmp_path / 'live.db')
    before = live.path.read_bytes()
    module = backups if mode == 'normal' else recovery
    copy = module._copy_database

    def changed_copy(src, dst):
        copy(src, dst)
        if phase == 'copy' and Path(src) == source.path:
            change(dst, 'categories', 'name', b'private-value')

    def changed_store(path):
        if phase == 'copy':
            pytest.fail('Invalid records reached Store/migrations')
        staged = Store(path)
        change(path, 'events', 'title', b'private-value')
        return staged

    monkeypatch.setattr(module, '_copy_database', changed_copy)
    monkeypatch.setattr(storage, 'Store', changed_store)
    with pytest.raises(ValueError, match='записи'):
        (backups.restore_backup(live, source.path) if mode == 'normal'
         else recovery.recover_database(live.path, source.path))
    assert live.path.read_bytes() == before
    assert not list(tmp_path.glob('.director-snapshot-*'))
    assert not list(tmp_path.glob('.recovery-*'))


@pytest.mark.parametrize('mode', ['normal', 'emergency'])
def test_valid_records_restore_open_and_preserve_plan_fact_history(tmp_path, mode):
    from PySide6.QtCore import QDate
    from PySide6.QtWidgets import QApplication
    from director_control.ui import MainWindow

    app = QApplication.instance() or QApplication([])
    source, eid = populated(tmp_path / 'source.db')
    # Historical plain text, non-object JSON and removed-event history remain supported.
    with source._connect() as con:
        for details in ('Historical plain text', '["old", 1]', '{"unknown":{"было":null,"стало":true}}'):
            con.execute('INSERT INTO audit(event_id,title,action,details,changed_at) VALUES (999,?,?,?,?)',
                        ('Deleted event', 'Legacy action', details, DAY + 'T09:00:00'))
    copy = backups.create_backup(source)
    live = Store(tmp_path / 'live.db')
    if mode == 'emergency':
        live.path.write_bytes(b'original damaged database')
    (backups.restore_backup(live, copy) if mode == 'normal' else recovery.recover_database(live.path, copy))
    updates.prepare_version_update(live.path)
    restored = Store(live.path)
    assert restored.get_event(eid) == source.get_event(eid)
    assert restored.baseline_rules() == source.baseline_rules()
    assert all(row in restored.audit_log() for row in source.audit_log())
    assert restored.analytics_report(DAY).totals.comparable == 1
    window = MainWindow(restored)
    try:
        window.date_input.setDate(QDate.fromString(DAY, 'yyyy-MM-dd'))
        window.reload()
        assert eid in window.row_ids
    finally:
        dispose_window(app, window)


@pytest.mark.parametrize('phase', ['validation', 'store', 'window'])
def test_startup_failure_offers_recovery_and_disposes_partial_window(tmp_path, monkeypatch, phase):
    from PySide6.QtWidgets import QApplication, QWidget
    from director_control import ui

    app = QApplication.instance() or QApplication([])
    source, _ = populated(tmp_path / 'live.db')
    before = source.path.read_bytes()
    previous_widgets = set(app.topLevelWidgets())
    offered = []
    partial = []
    monkeypatch.setattr(recovery, 'offer_recovery', lambda path, error: offered.append((path, type(error))))
    if phase == 'validation':
        change(source.path, 'categories', 'name', b'private-value')
        before = source.path.read_bytes()
    else:
        def fail(*args):
            if phase == 'window':
                partial.append(QWidget())
                partial[-1].setWindowTitle('Incomplete window')
            raise TypeError('synthetic startup failure')
        monkeypatch.setattr(ui, 'Store' if phase == 'store' else 'MainWindow', fail)
    assert ui._open_database_window(source.path) is None
    assert offered == [(source.path, ValueError if phase == 'validation' else TypeError)]
    assert set(app.topLevelWidgets()) == previous_widgets
    if partial:
        from shiboken6 import isValid
        assert not isValid(partial[0])
    assert source.path.read_bytes() == before


def test_json_structure_work_is_bounded(tmp_path):
    source, _ = populated(tmp_path / 'source.db')
    change(source.path, 'audit', 'details', json.dumps([0] * 100001))
    with pytest.raises(ValueError, match='записи'):
        backups.validate_database(source.path)


def test_gui_rejects_invalid_records_without_closing_or_changing_live_data(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    from tests.test_backup_ui import make_window, settle

    source, _ = populated(tmp_path / 'source.db')
    change(source.path, 'events', 'title', b'private-value')
    app, live, eid, window = make_window(tmp_path)
    before = live.path.read_bytes()
    warnings = []
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *args: (str(source.path), ''))
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: warnings.append(args[2]))
    try:
        window.backup_panel.restore_button.click()
        settle(app, window.backup_panel)
        assert warnings and 'записи' in warnings[-1]
        assert live.path.read_bytes() == before and window.isEnabled()
        assert not getattr(window, '_restored', False)
        live.update_event(eid, note='Still usable ' + date.today().isoformat())
        window.reload()
    finally:
        dispose_window(app, window)
