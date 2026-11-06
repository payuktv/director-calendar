"""Verified SQLite snapshots, daily retention and staged, atomic restoration."""
from datetime import datetime
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
from zoneinfo import ZoneInfo

from . import __version__
from . import database_guard as guard

SCHEMA_VERSION = 4


def _read_only(path, budget=None):
    guard.check_file_size(path)
    budget = budget or guard.Budget(guard.VALIDATION_SECONDS)
    con = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True, timeout=2)
    try:
        guard.configure_connection(con, inspection=True)
        con.set_progress_handler(budget.expired, 1000)
        return con
    except Exception:
        con.close()
        raise


def validate_database(path):
    """Reject foreign/corrupt/newer files before touching the working database."""
    budget = guard.Budget(guard.VALIDATION_SECONDS)
    try:
        with closing(_read_only(path, budget)) as con:
            con.execute('BEGIN')
            version = con.execute('PRAGMA user_version').fetchone()[0]
            if version > SCHEMA_VERSION:
                raise ValueError('Копия создана более новой версией приложения. Сначала обнови приложение.')
            # Never run integrity checks, data queries or migrations on foreign SQL.
            guard.validate_schema(con)
            tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            required = {'events', 'categories', 'settings', 'audit', 'day_freezes'}
            if version >= 2:
                required.add('calendar_events')
            if version >= 4:
                required |= {'baseline_rules', 'calendar_syncs'}
            if not required <= tables:
                raise ValueError('Это не резервная копия Director Calendar: отсутствуют таблицы приложения.')
            if con.execute('PRAGMA quick_check(1)').fetchall() != [('ok',)] or con.execute('PRAGMA foreign_key_check').fetchone():
                raise ValueError('В копии обнаружены повреждения или нарушенные связи записей.')
            fields = {row[1] for row in con.execute('PRAGMA table_info(events)')}
            if not {'id', 'title', 'category', 'source', 'status', 'note', 'external_key', 'created_at', 'updated_at',
                    'current_start', 'current_end', 'baseline_start', 'baseline_end', 'actual_start', 'actual_end'} <= fields:
                raise ValueError('В копии отсутствуют обязательные поля событий.')
            columns = {'categories': {'name', 'color', 'track'}, 'settings': {'key', 'value'},
                       'audit': {'id', 'event_id', 'title', 'action', 'details', 'changed_at'},
                       'day_freezes': {'day', 'frozen_at'}}
            if version >= 2:
                columns['calendar_events'] = {'event_id', 'calendar_key', 'uid', 'recurrence_id', 'missing',
                                             'cancelled', 'all_day', 'baseline_all_day', 'local_status'}
            if version >= 4:
                columns['baseline_rules'] = {'event_id', 'category', 'track', 'tolerance_minutes'}
                columns['calendar_syncs'] = {'id', 'calendar_key', 'start', 'end', 'status', 'finished_at'}
                if 'revision' not in fields:
                    raise ValueError('В копии отсутствует версия записи события.')
            for table, required_columns in columns.items():
                if not required_columns <= {row[1] for row in con.execute('PRAGMA table_info(' + table + ')')}:
                    raise ValueError('В копии отсутствуют обязательные поля приложения.')
            withdrawn = '''e.source='caldav' AND e.current_start IS NULL AND e.current_end IS NULL
                AND e.baseline_start IS NULL AND e.baseline_end IS NULL
                AND e.actual_start IS NULL AND e.actual_end IS NULL
                AND EXISTS (SELECT 1 FROM calendar_events m WHERE m.event_id=e.id AND m.missing=1)
                AND EXISTS (SELECT 1 FROM audit a WHERE a.event_id=e.id
                    AND a.action='Убрано из актуального плана Mail.ru')''' if 'calendar_events' in tables else '0'
            for row in con.execute('SELECT current_start,current_end,baseline_start,baseline_end,actual_start,actual_end,'
                                   'status,source,id,(' + withdrawn + ') FROM events e'):
                budget.check()
                if not row[0] and not row[4] and not row[9]:
                    raise ValueError('В копии есть событие без планового и фактического времени.')
                for start, end in zip(row[:6:2], row[1:6:2]):
                    if bool(start) != bool(end):
                        raise ValueError('В копии есть неполный интервал события.')
                    if start:
                        a, b = datetime.fromisoformat(start), datetime.fromisoformat(end)
                        if a.tzinfo is not None or b.tzinfo is not None or a >= b:
                            raise ValueError('В копии есть некорректное время события.')
                if row[6] not in {'pending', 'done', 'partial', 'cancelled', 'moved'} or row[7] not in {'local', 'caldav', 'manual'}:
                    raise ValueError('В копии есть неподдерживаемый статус или источник события.')
            if version >= 4 and con.execute('''SELECT 1 FROM events e LEFT JOIN baseline_rules b ON b.event_id=e.id
                    WHERE e.source IN ('local','caldav') AND e.baseline_start IS NOT NULL AND b.event_id IS NULL LIMIT 1''').fetchone():
                raise ValueError('В копии отсутствуют правила зафиксированного плана.')
            tolerance = con.execute("SELECT value FROM settings WHERE key='tolerance_minutes'").fetchone()
            if tolerance and not 0 <= int(tolerance[0]) <= 180:
                raise ValueError('В копии некорректные настройки контроля времени.')
            budget.check()
            return version
    except sqlite3.DatabaseError as exc:
        budget.check()
        raise ValueError('Не удалось прочитать резервную копию. Проверь, что выбран исправный файл базы данных.') from exc


def _copy_database(source, target):
    # Context managers commit, but sqlite3 connections must also be closed on Windows.
    budget = guard.Budget(guard.COPY_SECONDS)
    with closing(_read_only(source, budget)) as src, closing(sqlite3.connect(target)) as dst:
        guard.validate_schema(src)
        page_size = src.execute('PRAGMA page_size').fetchone()[0]
        def progress(status, remaining, total):
            budget.check()
            if total * page_size > guard.MAX_DATABASE_BYTES:
                raise ValueError('Размер базы превышает допустимые 512 МиБ.')
        src.backup(dst, pages=128, progress=progress)
        # Make every snapshot a self-contained file, including sources in WAL mode.
        if dst.execute('PRAGMA journal_mode=DELETE').fetchone()[0].lower() != 'delete':
            raise ValueError('Не удалось подготовить автономный файл резервной копии.')


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', value):
        raise ValueError('Некорректная сохранённая версия приложения. Выбери другую копию или обратись за помощью.')
    return tuple(int(part) for part in value.split('.'))


def validate_compatible_database(path, version=__version__):
    """Shared read-only gate for startup and both restore paths; return the stored version.

    A missing marker is supported for legacy copies. A present but invalid marker
    is rejected. Snapshot creation uses the same schema/data checks, but deliberately does not
    treat a snapshot as compatible with this application version.
    """
    current = version_tuple(version)
    validate_database(path)
    with closing(_read_only(path)) as con:
        row = con.execute("SELECT value FROM settings WHERE key='app_last_version'").fetchone()
    if row is None:
        return None
    previous = row[0]
    if version_tuple(previous) > current:
        raise ValueError(f'База уже открывалась в более новой версии v{previous}; установлена v{version}. '
                         'Сначала обнови приложение или выбери более старую совместимую копию.')
    return previous


def _temporary(folder):
    descriptor, name = tempfile.mkstemp(prefix='.director-snapshot-', suffix='.db', dir=folder)
    os.close(descriptor)
    return Path(name)


def _cleanup_temporary(path):
    for suffix in ('', '-wal', '-shm', '-journal'):
        Path(str(path) + suffix).unlink(missing_ok=True)


def database_key(store):
    return hashlib.sha256(os.path.normcase(str(store.path.resolve())).encode()).hexdigest()[:12]


def create_backup(store, folder=None, *, kind='manual', now=None):
    folder = Path(folder) if folder else store.path.parent / 'backups'
    folder.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now()).strftime('%Y%m%d-%H%M%S-%f')
    prefix = 'backup' if kind == 'manual' else f'{kind}-{database_key(store)}'
    destination = folder / f'{prefix}-{stamp}.db'
    temporary = _temporary(folder)
    try:
        _copy_database(store.path, temporary)
        validate_database(temporary)
        os.replace(temporary, destination)
        return destination
    finally:
        _cleanup_temporary(temporary)


def backup_folder(store):
    value = store.get_setting('backup_folder').strip()
    return Path(value).expanduser() if value else store.path.parent / 'backups'


def save_backup_settings(store, enabled, folder, keep):
    if not 1 <= int(keep) <= 365:
        raise ValueError('Количество автоматических копий: от 1 до 365.')
    folder = str(Path(folder).expanduser().resolve()) if folder.strip() else ''
    if folder and Path(folder).exists() and not Path(folder).is_dir():
        raise ValueError('Для копий нужно выбрать папку.')
    values = {'backup_auto': '1' if enabled else '0', 'backup_folder': folder, 'backup_keep': str(keep)}
    with store._connect() as con:
        con.execute('BEGIN IMMEDIATE')
        changes = {}
        for key, value in values.items():
            old = con.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
            if not old or old['value'] != value:
                changes[key] = {'было': old['value'] if old else None, 'стало': value}
            con.execute('INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, value))
        if changes:
            store._audit(con, None, 'Резервное копирование', 'Настройки копирования', changes)


def _prune(store, folder):
    keep = int(store.get_setting('backup_keep', '30'))
    if not 1 <= keep <= 365:
        raise ValueError('Некорректное количество автоматических копий.')
    pattern = re.compile(r'auto-' + database_key(store) + r'-\d{8}-\d{6}-\d{6}\.db$')
    owned = sorted((p for p in folder.glob('auto-*.db') if pattern.fullmatch(p.name)), reverse=True)
    for path in owned[keep:]:
        path.unlink()


def scheduled_backup(store, now=None):
    if store.get_setting('backup_auto', '1') != '1':
        return None
    now = now or datetime.now(ZoneInfo(store.get_setting('mail_timezone', 'Europe/Moscow')))
    day = now.date().isoformat()
    folder = backup_folder(store).resolve()
    try:
        last = json.loads(store.get_setting('backup_last_auto', '{}'))
    except (TypeError, ValueError):
        last = {}
    if not isinstance(last, dict):
        last = {}
    if last.get('day') == day and last.get('folder') == str(folder) and Path(last.get('path', '')).is_file():
        _prune(store, folder)
        return None
    saved = create_backup(store, folder, kind='auto', now=now)
    store.set_setting('backup_last_auto', json.dumps({'day': day, 'folder': str(folder), 'path': str(saved)}, ensure_ascii=False))
    _prune(store, folder)
    return saved


def restore_backup(store, source):
    source = Path(source).resolve()
    if source == store.path.resolve():
        raise ValueError('Выбери резервную копию, а не открытую рабочую базу.')
    validate_compatible_database(source)
    safety = create_backup(store, kind='before-restore')
    temporary = _temporary(store.path.parent)
    try:
        _copy_database(source, temporary)
        validate_compatible_database(temporary)
        from .storage import Store
        staged = Store(temporary)
        with staged._connect() as con:
            staged._audit(con, None, 'База данных', 'Восстановление из копии',
                          {'копия': source.name, 'страховая копия': str(safety)})
        validate_compatible_database(temporary)
        # No app worker may use the target while restoration runs. Checkpoint any
        # existing WAL before swapping the file, so old pages cannot reappear.
        con = sqlite3.connect(store.path, timeout=1)
        try:
            if con.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()[0] != 0:
                raise ValueError('База занята другим процессом. Закрой остальные экземпляры приложения.')
        finally:
            con.close()
        for suffix in ('-wal', '-shm', '-journal'):
            if Path(str(store.path) + suffix).exists():
                raise ValueError('База занята другим процессом. Повтори восстановление после его закрытия.')
        temporary.chmod(store.path.stat().st_mode & 0o777)
        os.replace(temporary, store.path)
        return safety
    finally:
        _cleanup_temporary(temporary)
