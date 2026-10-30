"""Explicit diagnostic for the shipped bundle; uses only temporary synthetic data."""
import json
import os
from pathlib import Path
import tempfile
from uuid import uuid4


def verify_installation(destination):
    from . import __version__
    from .mail_calendar import CalendarConfig, parse_calendars
    from .desktop import app_icon_path, shortcut_spec
    from .storage import Store
    from .backups import create_backup, restore_backup
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QIcon
    from PySide6.QtCore import QTimer
    from .ui import MainWindow
    import certifi
    from datetime import date
    from zoneinfo import ZoneInfo
    from keyring.backends.Windows import WinVaultKeyring
    report = {'version': __version__, 'ok': False}
    # Resolve before any working-directory changes. This command never opens the user's DB.
    destination = Path(destination).resolve()
    with tempfile.TemporaryDirectory(prefix='DirectorCalendar-check-') as temporary:
        os.environ['DIRECTOR_CONTROL_DATA_DIR'] = temporary
        assert ZoneInfo('Europe/Moscow')
        assert Path(certifi.where()).is_file()
        config = CalendarConfig('https://calendar.mail.ru/test/', 'synthetic@example.test')
        sample = 'BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:bundle-check\r\nDTSTART:20261029T090000Z\r\nDTEND:20261029T100000Z\r\nSUMMARY:Test\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n'
        assert len(parse_calendars([sample], config, date(2026, 10, 29), date(2026, 10, 30)).events) == 1
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
        store = Store(Path(temporary) / 'test.db')
        eid = store.create_event('Synthetic', 'Работа', actual_start='2026-10-29T09:00:00', actual_end='2026-10-29T10:00:00')
        copy = create_backup(store)
        store.update_event(eid, note='change')
        restore_backup(store, copy)
        assert store.get_event(eid).note == ''
        window = MainWindow(store)
        window.show()
        QTimer.singleShot(500, window.close)
        app.exec()
        import sys
        report.update(ok=True, frozen=bool(getattr(sys, 'frozen', False)),
                      shortcut_target=str(shortcut_spec().target), icon=True,
                      caldav_parse=True, vault=True, backup_restore=True, gui=True)
    destination.write_text(json.dumps(report), encoding='utf-8')
    return 0
