"""Restored settings must be safe to open and cannot select a backup destination."""
from contextlib import closing
from datetime import datetime
import json
from pathlib import Path
import sqlite3

import pytest

from director_control import __version__, backups, recovery, storage, updates
from director_control.storage import Store


def restore(mode, live, source):
    if mode == 'normal':
        return backups.restore_backup(live, source)
    return recovery.recover_database(live.path, source)


def set_raw(path, key, value):
    with closing(sqlite3.connect(path)) as con:
        con.execute('INSERT OR REPLACE INTO settings VALUES (?, ?)', (key, value))
        con.commit()


def dispose_window(app, window):
    from PySide6.QtCore import QEvent
    window.close()
    window.deleteLater()
    # close() only hides the widget; retained windows make later theme tests
    # repeatedly restyle every old calendar and can exhaust the CI time budget.
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


@pytest.mark.parametrize('mode', ['normal', 'emergency', 'startup'])
@pytest.mark.parametrize(('key', 'value'), [
    ('backup_keep', 'not-an-integer'), ('backup_keep', '0'), ('backup_keep', '366'),
    ('backup_keep', b'30'), ('tolerance_minutes', '181'), ('backup_auto', 'yes'),
    ('mail_auto', 'true'), ('mail_timezone', 'Unknown/Invalid'), ('mail_timezone', '../UTC'),
    ('mail_timezone', r'\\untrusted.invalid\share'),
    ('mail_url', b'https://calendar.mail.ru/test/'), ('backup_folder', 'bad\0path'),
    ('backup_last_auto', '[]'), ('backup_last_auto', '{"day":[]}'),
    ('backup_last_auto', '{"day":"2026-02-30","folder":"","path":""}'),
    ('backup_last_auto', '{"day":"2026-11-06","folder":{},"path":[]}'),
    ('backup_last_auto', '[' * 1100 + ']' * 1100), ('ui_theme', 'unknown'),
])
def test_invalid_settings_rejected_without_changing_files(tmp_path, mode, key, value):
    source = Store(tmp_path / 'source.db')
    source.set_setting('app_last_version', __version__)
    set_raw(source.path, key, value)
    live = Store(tmp_path / 'live.db')
    if mode == 'emergency':
        live.path.write_bytes(b'original damaged database')
        Path(str(live.path) + '-wal').write_bytes(b'original journal')
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    with pytest.raises(ValueError, match='настройк'):
        if mode == 'startup':
            updates.prepare_version_update(source.path)
        else:
            restore(mode, live, source.path)
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before


@pytest.mark.parametrize('mode', ['normal', 'emergency'])
@pytest.mark.parametrize('enabled', [True, False])
def test_restored_app_uses_only_local_backup_policy(tmp_path, mode, enabled):
    from PySide6.QtWidgets import QApplication
    from director_control.ui import MainWindow

    app = QApplication.instance() or QApplication([])
    source = Store(tmp_path / 'source.db')
    source.set_setting('app_last_version', __version__)
    source.set_setting('ui_theme', 'dark')
    source.set_setting('backup_folder', str(tmp_path / 'imported-destination'))
    source.set_setting('backup_auto', '0' if enabled else '1')
    source.set_setting('backup_keep', '1')
    now = datetime(2026, 11, 6, 12)
    source.set_setting('backup_last_auto', json.dumps({
        'day': now.date().isoformat(), 'folder': source.get_setting('backup_folder'),
        'path': str(tmp_path / 'imported-last-copy.db')}))
    source_bytes = source.path.read_bytes()
    live = Store(tmp_path / 'live.db')
    local_folder = tmp_path / 'user-selected-destination'
    backups.save_backup_settings(live, enabled, str(local_folder), 7)
    if enabled:
        backups.scheduled_backup(live, now)
    if mode == 'emergency':
        live.path.write_bytes(b'original damaged database')
    safety = restore(mode, live, source.path)
    assert safety.exists() and source.path.read_bytes() == source_bytes
    assert updates.prepare_version_update(live.path) is None
    restored = Store(live.path)
    assert restored.get_setting('backup_last_auto') == ''
    assert restored.get_setting('ui_theme') == 'dark'
    assert restored.get_setting('backup_keep') == ('7' if mode == 'normal' else '30')
    assert restored.get_setting('backup_auto') == ('1' if enabled or mode == 'emergency' else '0')
    expected_folder = local_folder if mode == 'normal' else tmp_path / 'backups'
    assert backups.backup_folder(restored) == expected_folder
    window = MainWindow(restored)
    try:
        assert window.backup_panel.keep.value() == (7 if mode == 'normal' else 30)
        eid = restored.create_event('New after restore', 'Работа',
                                   '2026-11-07T09:00:00', '2026-11-07T10:00:00')
        saved = backups.scheduled_backup(restored, now)
        if enabled or mode == 'emergency':
            assert saved.parent == expected_folder
            with closing(sqlite3.connect(saved)) as con:
                assert con.execute('SELECT title FROM events WHERE id=?', (eid,)).fetchone()[0] == 'New after restore'
        else:
            assert saved is None
        assert not (tmp_path / 'imported-destination').exists()
        assert updates.prepare_version_update(live.path) is None
    finally:
        dispose_window(app, window)


@pytest.mark.parametrize('mode', ['normal', 'emergency'])
def test_imported_network_paths_are_never_accessed(tmp_path, monkeypatch, mode):
    source = Store(tmp_path / 'source.db')
    remote = r'\\untrusted.invalid\share'
    source.set_setting('backup_folder', remote)
    source.set_setting('backup_last_auto', json.dumps({
        'day': '2026-11-06', 'folder': remote, 'path': remote + r'\copy.db'}))
    live = Store(tmp_path / 'live.db')
    # Stop before any OS/network access, including calls that only inspect a path.
    for name in ('resolve', 'stat', 'mkdir', 'glob', 'open'):
        original = getattr(Path, name)
        def guarded(path, *args, _original=original, **kwargs):
            if 'untrusted.invalid' in str(path):
                pytest.fail('Imported network path reached the filesystem')
            return _original(path, *args, **kwargs)
        monkeypatch.setattr(Path, name, guarded)
    restore(mode, live, source.path)
    saved = backups.scheduled_backup(Store(live.path), datetime(2026, 11, 6, 12))
    assert saved.parent == tmp_path / 'backups'


@pytest.mark.parametrize('mode', ['normal', 'emergency'])
@pytest.mark.parametrize('phase', ['copy', 'migration'])
def test_staging_settings_rechecked_before_replacement(tmp_path, monkeypatch, mode, phase):
    source = Store(tmp_path / 'source.db').path
    live = Store(tmp_path / 'live.db')
    before = live.path.read_bytes()
    module = backups if mode == 'normal' else recovery
    copy = module._copy_database

    def changed_copy(src, dst):
        copy(src, dst)
        if Path(src) == source:
            set_raw(dst, 'mail_timezone', 'Unknown/Invalid')

    def changed_store(path):
        if phase == 'copy':
            pytest.fail('Invalid staging settings reached migrations')
        store = Store(path)
        store.set_setting('mail_timezone', 'Unknown/Invalid')
        return store

    if phase == 'copy':
        monkeypatch.setattr(module, '_copy_database', changed_copy)
    monkeypatch.setattr(storage, 'Store', changed_store)
    with pytest.raises(ValueError, match='настройк'):
        restore(mode, live, source)
    assert live.path.read_bytes() == before
    assert not list(tmp_path.glob('.director-snapshot-*'))
    assert not list(tmp_path.glob('.recovery-*'))


def test_gui_rejects_bad_settings_and_stays_usable(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    from tests.test_backup_ui import make_window, settle

    app, live, eid, window = make_window(tmp_path)
    source = Store(tmp_path / 'bad.db')
    source.set_setting('backup_keep', 'not-an-integer')
    before = live.path.read_bytes()
    warnings = []
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *args: (str(source.path), ''))
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: warnings.append(args[2]))
    window.show()
    try:
        window.backup_panel.restore_button.click()
        settle(app, window.backup_panel)
        assert window.isVisible() and window.isEnabled()
        assert window.backup_panel.restore_button.isEnabled()
        assert warnings and 'настройк' in warnings[0]
        assert live.path.read_bytes() == before and live.get_event(eid).title == 'Исходное событие'
    finally:
        dispose_window(app, window)
