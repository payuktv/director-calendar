"""Explicit diagnostic for the shipped bundle; uses only temporary synthetic data."""
import json
from contextlib import closing
import os
import sqlite3
from pathlib import Path
import tempfile
from uuid import uuid4


def _verify_restored_settings(folder):
    from datetime import datetime
    from . import __version__
    from .storage import Store
    from .backups import restore_backup, save_backup_settings, scheduled_backup
    from .recovery import recover_database
    from .updates import prepare_version_update

    folder = folder.resolve()
    source = Store(folder / 'settings-source.db')
    source.set_setting('app_last_version', __version__)
    imported_folder = folder / 'imported-destination'
    source.set_setting('backup_folder', str(imported_folder))
    source.set_setting('backup_keep', '1')
    now = datetime(2026, 11, 6, 12)
    source.set_setting('backup_last_auto', json.dumps({
        'day': now.date().isoformat(), 'folder': str(imported_folder),
        'path': str(imported_folder / 'old.db')}))
    source_bytes = source.path.read_bytes()
    for emergency in (False, True):
        live = Store(folder / f'settings-target-{emergency}.db')
        selected = folder / 'locally-selected-destination'
        save_backup_settings(live, True, str(selected), 7)
        if emergency:
            live.path.write_bytes(b'synthetic damaged database')
            recover_database(live.path, source.path)
        else:
            restore_backup(live, source.path)
        assert prepare_version_update(live.path) is None
        live = Store(live.path)
        assert live.get_setting('backup_keep') == ('30' if emergency else '7')
        assert not live.get_setting('backup_last_auto')
        eid = live.create_event('New after restore', 'Работа', '2026-11-07T09:00:00', '2026-11-07T10:00:00')
        saved = scheduled_backup(live, now)
        assert saved.parent == (folder / 'backups' if emergency else selected)
        with closing(sqlite3.connect(saved)) as con:
            assert con.execute('SELECT title FROM events WHERE id=?', (eid,)).fetchone()[0] == 'New after restore'
    assert source.path.read_bytes() == source_bytes and not imported_folder.exists()
    source.set_setting('backup_keep', 'not-an-integer')
    before = live.path.read_bytes()
    for restore in (lambda: restore_backup(live, source.path),
                    lambda: recover_database(live.path, source.path),
                    lambda: prepare_version_update(source.path)):
        try:
            restore()
        except ValueError:
            pass
        else:
            raise AssertionError('Invalid backup settings were accepted')
        assert live.path.read_bytes() == before


def _verify_restored_records(folder):
    from . import __version__
    from .storage import Store
    from .backups import restore_backup
    from .recovery import recover_database
    from .updates import prepare_version_update

    live = Store(folder / 'records-live.db')
    for case in ('category', 'title', 'tolerance'):
        source = Store(folder / ('records-' + case + '.db'))
        source.set_setting('app_last_version', __version__)
        eid = source.create_event('Synthetic', 'Работа', '2026-11-12T09:00:00', '2026-11-12T10:00:00')
        source.freeze_day('2026-11-12')
        with closing(sqlite3.connect(source.path)) as con:
            if case == 'category':
                con.execute('INSERT INTO categories VALUES (?,?,?)', (b'Synthetic', '#123456', 1))
            elif case == 'title':
                con.execute('UPDATE events SET title=? WHERE id=?', (b'Synthetic', eid))
            else:
                con.execute('UPDATE baseline_rules SET tolerance_minutes=? WHERE event_id=?', ('invalid', eid))
            con.commit()
        before = live.path.read_bytes(), source.path.read_bytes()
        for restore in (lambda: restore_backup(live, source.path),
                        lambda: recover_database(live.path, source.path),
                        lambda: prepare_version_update(source.path)):
            try:
                restore()
            except ValueError:
                pass
            else:
                raise AssertionError('Malformed application records were accepted')
            assert (live.path.read_bytes(), source.path.read_bytes()) == before


def _verify_calendar_writes(folder):
    """Exercise write/reopen consistency using the shipped child process."""
    from dataclasses import replace
    from datetime import date
    from . import __version__
    from .mail_calendar import CalendarConfig, CalendarError
    from .storage import Store
    from .sync_process import parse_isolated
    from .updates import prepare_version_update

    store = Store(folder / 'calendar-writes.db')
    store.set_setting('app_last_version', __version__)
    config = CalendarConfig('https://calendar.mail.ru/test/', 'synthetic@example.test')
    start, end = date(2026, 11, 12), date(2026, 11, 13)
    sample = ('BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:valid\r\n'
              'DTSTART:20261112T090000Z\r\nDTEND:20261112T100000Z\r\n'
              'SUMMARY:Synthetic\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n')
    snapshot = parse_isolated([sample], config, start, end)
    assert store.apply_calendar_snapshot(snapshot)['added'] == 1
    assert prepare_version_update(store.path) is None
    before = store.path.read_bytes()
    for uid in ('   ', r'\n'):
        try:
            parse_isolated([sample.replace('UID:valid', 'UID:' + uid)], config, start, end)
        except CalendarError:
            pass
        else:
            raise AssertionError('Invalid UID accepted by the shipped worker')
    invalid = replace(snapshot, events=(replace(snapshot.events[0], uid='   '),))
    for write in (lambda: store.apply_calendar_snapshot(invalid),
                  lambda: store.update_event(store.daily_events('2026-11-12')[0].id, note='invalid\0note')):
        try:
            write()
        except ValueError:
            pass
        else:
            raise AssertionError('Write accepted data rejected at startup')
        assert store.path.read_bytes() == before
    store.apply_calendar_snapshot(replace(snapshot, events=()))
    assert prepare_version_update(store.path) is None


def verify_installation(destination):
    from . import diagnostics
    from . import __version__
    from .runtime_versions import runtime_versions, verify_runtime, verify_xml_runtime
    from .mail_calendar import CalendarConfig
    from .sync_process import parse_isolated
    from .desktop import app_icon_path, shortcut_spec
    from .storage import Store
    from .backups import create_backup, restore_backup
    from .recovery import recover_database
    from .updates import prepare_version_update, record_version
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QIcon
    from PySide6.QtCore import QTimer
    from .ui import MainWindow
    import certifi
    from datetime import date
    from zoneinfo import ZoneInfo
    from keyring.backends.Windows import WinVaultKeyring
    # Resolve before any working-directory changes. This command never opens the user's DB.
    destination = Path(destination).resolve()
    report = {'version': __version__, 'ok': False}
    report.update(runtime_versions())
    try:
        verify_runtime(report)
    except ValueError:
        # Native version numbers are safe diagnostic data, including on failure.
        destination.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        return 1
    report['runtime_patched'] = True
    verify_xml_runtime()
    report['xml_runtime_verified'] = True
    sqlite_source = sqlite3.connect(':memory:')
    try:
        source_id = sqlite_source.execute('SELECT sqlite_source_id()').fetchone()[0]
    finally:
        sqlite_source.close()
    assert sqlite3.sqlite_version == '3.54.1'
    assert source_id == '2026-10-16 14:45:20 555e07ef33f69a0957d24d8e555b702464a131d6f1607f4c3c1e4551e8e6ca76'
    report.update(sqlite_patched=True, sqlite_version=sqlite3.sqlite_version, sqlite_source_id=source_id)
    with tempfile.TemporaryDirectory(prefix='DirectorCalendar-check-') as temporary, diagnostics.session(Path(temporary) / 'logs'):
        os.environ['DIRECTOR_CONTROL_DATA_DIR'] = temporary
        _verify_restored_settings(Path(temporary))
        _verify_restored_records(Path(temporary))
        _verify_calendar_writes(Path(temporary))
        report.update(backup_settings_validated=True, backup_destination_local=True)
        report['backup_records_validated'] = True
        report['calendar_writes_validated'] = True
        assert ZoneInfo('Europe/Moscow')
        assert Path(certifi.where()).is_file()
        config = CalendarConfig('https://calendar.mail.ru/test/', 'synthetic@example.test')
        sample = 'BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:bundle-check\r\nDTSTART:20261029T090000Z\r\nDTEND:20261029T100000Z\r\nSUMMARY:Test\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n'
        assert len(parse_isolated([sample], config, date(2026, 10, 29), date(2026, 10, 30)).events) == 1
        backend = WinVaultKeyring()
        account = str(uuid4())
        try:
            backend.set_password('DirectorCalendar.DistributionCheck', account, 'synthetic-test-value')
            assert backend.get_password('DirectorCalendar.DistributionCheck', account) == 'synthetic-test-value'
        finally:
            backend.delete_password('DirectorCalendar.DistributionCheck', account)
        app = QApplication.instance() or QApplication([])
        app.setWindowIcon(QIcon(str(app_icon_path())))
        assert not app.windowIcon().isNull()
        try:
            raise RuntimeError('synthetic-password-must-not-be-logged')
        except RuntimeError as exc:
            assert diagnostics.record_error('diagnostics.self_test', exc)
        logged = diagnostics.log_path().read_text(encoding='utf-8')
        assert 'synthetic-password-must-not-be-logged' not in logged
        assert json.loads(logged.splitlines()[-1])['exceptions'][0]['type'] == 'RuntimeError'
        store = Store(Path(temporary) / 'test.db')
        record_version(store)
        eid = store.create_event('Synthetic', 'Работа', actual_start='2026-10-29T09:00:00', actual_end='2026-10-29T10:00:00')
        copy = create_backup(store)
        store.update_event(eid, note='change')
        restore_backup(store, copy)
        assert prepare_version_update(store.path) is None
        assert store.get_event(eid).note == ''
        # Both restoration entry points must reject active SQL before touching data.
        for attack in ('trigger', 'fts', 'view'):
            malicious = create_backup(store)
            with closing(sqlite3.connect(malicious)) as con:
                if attack == 'fts':
                    con.execute('CREATE VIRTUAL TABLE foreign_fts USING fts5(content)')
                elif attack == 'view':
                    con.execute('CREATE VIEW foreign_view AS SELECT * FROM events')
                else:
                    con.execute('CREATE TRIGGER erase AFTER INSERT ON audit BEGIN DELETE FROM events; END')
                con.commit()
            before_attack = store.path.read_bytes()
            for restore in (lambda: restore_backup(store, malicious),
                            lambda: recover_database(store.path, malicious)):
                try:
                    restore()
                except ValueError:
                    pass
                else:
                    raise AssertionError('An untrusted backup schema was accepted')
                assert store.path.read_bytes() == before_attack
        report['untrusted_backup_rejected'] = True
        future = Store(Path(temporary) / 'future.db')
        future.set_setting('app_last_version', '99.0.0')
        incompatible = create_backup(future)
        before = store.path.read_bytes()
        for restore in (lambda: restore_backup(store, incompatible),
                        lambda: recover_database(store.path, incompatible)):
            try:
                restore()
            except ValueError as exc:
                assert 'v99.0.0' in str(exc)
            else:
                raise AssertionError('An incompatible backup was accepted')
            assert store.path.read_bytes() == before
        store.path.write_bytes(b'synthetic damaged database')
        recover_database(store.path, copy)
        assert prepare_version_update(store.path) is None
        store = Store(store.path)
        assert store.get_event(eid).note == ''
        window = MainWindow(store)
        window.show()
        diagnostics.install_hooks()
        def synthetic_slot_error():
            raise RuntimeError('synthetic-gui-password-must-not-be-logged')
        QTimer.singleShot(0, synthetic_slot_error)
        QTimer.singleShot(500, window.close)
        app.exec()
        logged = diagnostics.log_path().read_text(encoding='utf-8')
        assert 'synthetic-gui-password-must-not-be-logged' not in logged
        assert any(json.loads(line)['operation'] == 'uncaught.gui' for line in logged.splitlines())
        import sys
        report.update(ok=True, frozen=bool(getattr(sys, 'frozen', False)),
                      shortcut_target=str(shortcut_spec().target), icon=True,
                      caldav_parse=True, vault=True, backup_restore=True,
                      backup_compatibility=True, emergency_restore=True, runtime_logging=True, gui=True)
    destination.write_text(json.dumps(report), encoding='utf-8')
    return 0
