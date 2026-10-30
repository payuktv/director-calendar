"""Preserve the existing local database before a different application version opens it."""
from contextlib import closing
from pathlib import Path
import sqlite3
from types import SimpleNamespace

from . import __version__
from .backups import create_backup, validate_database


def version_tuple(value):
    parts = value.split('.')
    if len(parts) != 3 or any(not p.isdigit() for p in parts):
        raise ValueError('Некорректная сохранённая версия приложения.')
    return tuple(int(p) for p in parts)


def prepare_version_update(database, version=__version__):
    """Call with the single-instance database lock held, BEFORE Store/migrations."""
    database = Path(database)
    current = version_tuple(version)
    if not database.exists():
        return None
    validate_database(database)
    with closing(sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True)) as con:
        row = con.execute("SELECT value FROM settings WHERE key='app_last_version'").fetchone()
    previous = row[0] if row else None
    if previous and version_tuple(previous) > current:
        raise ValueError('Эта база уже открывалась более новой версией приложения. Установи последнюю версию.')
    if previous == version:
        return None
    # Do not initialize or migrate the live database until a verified copy exists.
    return create_backup(SimpleNamespace(path=database), kind='before-update')


def record_version(store, version=__version__):
    if store.get_setting('app_last_version') != version:
        store.set_setting('app_last_version', version)
