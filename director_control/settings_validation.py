"""Validate imported settings without accessing paths supplied by a database."""
from datetime import date, datetime
import json
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


_CHOICES = {
    **{key: {'0', '1'} for key in ('backup_auto', 'mail_auto', 'mail_remember', 'ui_analytics_only_tracked')},
    'ui_theme': {'light', 'dark'},
    'ui_calendar_view': {'day', 'week', 'month', 'agenda'},
    'ui_analytics_mode': {'day', 'week', 'month'},
    'ui_history_page_size': {'50', '100', '200'},
}
_RANGES = {'backup_keep': (1, 365), 'tolerance_minutes': (0, 180)}


def _last_backup(value):
    # Bound JSON parsing separately from SQLite's larger general value limit.
    if len(value) > 131072:
        raise ValueError
    last = json.loads(value)
    if not isinstance(last, dict):
        raise ValueError
    if not last:
        return
    if set(last) != {'day', 'folder', 'path'}:
        raise ValueError
    if any(not isinstance(item, str) or '\0' in item for item in last.values()):
        raise ValueError
    if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', last['day']):
        raise ValueError
    date.fromisoformat(last['day'])
    if len(last['folder']) > 32767 or len(last['path']) > 32767:
        raise ValueError
    # In particular, do not resolve/stat either path, including UNC paths.


def validate_settings(con, budget):
    """Missing keys retain historical defaults; unknown text keys remain compatible."""
    for key, value in con.execute('SELECT key,value FROM settings'):
        budget.check()
        try:
            if not isinstance(key, str) or not isinstance(value, str) or '\0' in key or '\0' in value:
                raise ValueError
            if key in _RANGES:
                low, high = _RANGES[key]
                if not re.fullmatch(r'[0-9]{1,3}', value) or not low <= int(value) <= high:
                    raise ValueError
            elif key in _CHOICES and value not in _CHOICES[key]:
                raise ValueError
            elif key == 'mail_timezone':
                if len(value) > 256 or not re.fullmatch(r'[A-Za-z0-9_+-]+(?:/[A-Za-z0-9_+-]+)*', value):
                    raise ValueError
                ZoneInfo(value)
            elif key == 'mail_last_sync' and value:
                datetime.fromisoformat(value)
            elif key == 'backup_folder' and len(value) > 32767:
                raise ValueError
            elif key == 'backup_last_auto':
                _last_backup(value)
        except (ValueError, TypeError, RecursionError, ZoneInfoNotFoundError, OSError):
            # No raw setting values (paths or account details) in the error.
            raise ValueError('В базе некорректные настройки приложения. Выбери другую резервную копию.') from None
