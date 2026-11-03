"""Bounded local diagnostics. Never serialize exception messages, source lines or locals."""
from datetime import datetime, timezone
from contextlib import contextmanager
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import platform
import re
import sys
import threading

from . import __version__
from .storage import default_data_dir

MAX_BYTES = 1024 * 1024
BACKUP_COUNT = 3
OPERATIONS = frozenset({
    'startup', 'database.startup', 'uncaught.gui', 'uncaught.thread', 'uncaught.unraisable',
    'mail.fetch', 'mail.configure', 'mail.start', 'mail.apply', 'mail.record_failure',
    'credentials.read', 'credentials.write', 'backup.manual', 'backup.auto', 'backup.restore',
    'backup.settings', 'recovery.restore', 'history.load', 'analytics.calculate', 'analytics.export',
    'ui.action', 'diagnostics.open', 'diagnostics.self_test',
})
_lock = threading.RLock()
_handler = None
_path = None
_available = False
_previous_hooks = None
_notifier = None


class SafeRotatingHandler(RotatingFileHandler):
    def handleError(self, record):
        # logging's default handler prints the failing record to stderr. Do not.
        record.written = False


def log_path():
    return _path if _path is not None else default_data_dir() / 'logs' / 'director-calendar.log'


def available():
    return _available


def configure(folder=None):
    global _handler, _path, _available
    with _lock:
        if _handler is not None:
            try:
                _handler.close()
            except OSError:
                pass
            _handler = None
        _available = False
        try:
            _path = (Path(folder) if folder is not None else default_data_dir() / 'logs') / 'director-calendar.log'
            _path.parent.mkdir(parents=True, exist_ok=True)
            _handler = SafeRotatingHandler(_path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT,
                                           encoding='utf-8', errors='backslashreplace')
            _handler.setFormatter(logging.Formatter('%(message)s'))
            _available = True
        except (OSError, ValueError):
            pass
        return _available


def _identifier(value, fallback):
    return value if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.<>-]{1,80}', value) else fallback


def exception_details(error, traceback=None):
    """Use only code locations, types and numeric OS/SQLite codes; no str/repr(error)."""
    result, seen = [], set()
    pending = [(error, traceback)]
    while pending and len(result) < 4:
        current, tb = pending.pop(0)
        if current is None or id(current) in seen:
            continue
        seen.add(id(current))
        frames = []
        tb = tb if tb is not None else current.__traceback__
        while tb is not None:
            code = tb.tb_frame.f_code
            filename = code.co_filename.replace('\\', '/').rsplit('/', 1)[-1]
            frames.append({'file': _identifier(filename, '<module>'),
                           'function': _identifier(code.co_name, '<function>'), 'line': tb.tb_lineno})
            frames = frames[-12:]
            tb = tb.tb_next
        detail = {'type': _identifier(type(current).__name__, 'Exception'), 'frames': frames}
        for key in ('errno', 'sqlite_errorcode'):
            value = getattr(current, key, None)
            if type(value) is int and 0 <= value <= 65535:
                detail[key] = value
        result.append(detail)
        chained = current.__cause__ or (None if current.__suppress_context__ else current.__context__)
        if chained is not None:
            pending.append((chained, None))
        if isinstance(current, BaseExceptionGroup):
            pending.extend((child, None) for child in current.exceptions[:4])
    return result


def record_error(operation, error=None, traceback=None):
    """Best effort, never raise into the caller. Returns whether this record was written."""
    global _available
    try:
        with _lock:
            if _handler is None:
                return False
            payload = {'time': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                       'version': 'v' + __version__, 'platform': platform.system(),
                       'operation': operation if operation in OPERATIONS else 'ui.action',
                       'exceptions': exception_details(error if error is not None else sys.exc_info()[1], traceback)}
            record = logging.LogRecord('director-calendar', logging.ERROR, '', 0,
                                       json.dumps(payload, ensure_ascii=True), (), None)
            record.written = True
            _handler.handle(record)
            _available = record.written
            return record.written
    except Exception:
        _available = False
        return False


def set_notifier(callback):
    global _notifier
    _notifier = callback


def _uncaught(operation, error, tb):
    written = record_error(operation, error, tb)
    if _notifier is not None:
        try:
            _notifier(written)
        except Exception:
            pass


def _sys_hook(kind, error, tb):
    if issubclass(kind, (KeyboardInterrupt, SystemExit)):
        if _previous_hooks is not None:
            _previous_hooks[0](kind, error, tb)
        return
    _uncaught('uncaught.gui', error, tb)


def _thread_hook(args):
    if args.exc_type is not SystemExit:
        _uncaught('uncaught.thread', args.exc_value, args.exc_traceback)


def _unraisable_hook(args):
    _uncaught('uncaught.unraisable', args.exc_value, args.exc_traceback)


def install_hooks():
    global _previous_hooks
    if _previous_hooks is None:
        _previous_hooks = (sys.excepthook, threading.excepthook, sys.unraisablehook)
        sys.excepthook, threading.excepthook, sys.unraisablehook = _sys_hook, _thread_hook, _unraisable_hook


def shutdown():
    global _handler, _available, _previous_hooks, _notifier, _path
    with _lock:
        if _previous_hooks is not None:
            for obj, name, ours, previous in zip((sys, threading, sys),
                    ('excepthook', 'excepthook', 'unraisablehook'),
                    (_sys_hook, _thread_hook, _unraisable_hook), _previous_hooks):
                if getattr(obj, name) is ours:
                    setattr(obj, name, previous)
            _previous_hooks = None
        if _handler is not None:
            try:
                _handler.close()
            except OSError:
                pass
        _handler, _path, _notifier, _available = None, None, None, False


@contextmanager
def session(folder):
    configure(folder)
    try:
        yield
    finally:
        shutdown()
