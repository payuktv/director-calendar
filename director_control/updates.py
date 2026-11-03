"""Preserve the existing local database before a different application version opens it."""
from pathlib import Path
from types import SimpleNamespace

from . import __version__
from .backups import create_backup, validate_compatible_database, version_tuple


def prepare_version_update(database, version=__version__):
    """Call with the single-instance database lock held, BEFORE Store/migrations."""
    database = Path(database)
    version_tuple(version)
    if not database.exists():
        return None
    previous = validate_compatible_database(database, version)
    if previous == version:
        return None
    # Do not initialize or migrate the live database until a verified copy exists.
    return create_backup(SimpleNamespace(path=database), kind='before-update')


def record_version(store, version=__version__):
    if store.get_setting('app_last_version') != version:
        store.set_setting('app_last_version', version)
