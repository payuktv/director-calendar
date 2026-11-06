"""Disposable, resource-limited CalDAV worker. Never opens the application DB.

Credentials and results travel through private pipes, never command arguments or
temporary files. Only the GUI process can commit a fully received snapshot.
"""
from dataclasses import asdict
from datetime import date
import json
import os
from pathlib import Path
import subprocess
import sys
from time import monotonic

MAX_MEMORY = 512 * 1024 * 1024
CPU_SECONDS = 20
MAX_MESSAGE = 32 * 1024 * 1024
SYNC_SECONDS = 60
_job_handle = None


def limit_resources(limit=MAX_MEMORY):
    """Fail closed if the OS cannot enforce the worker's memory ceiling."""
    if sys.platform == 'win32':
        import ctypes as c
        from ctypes import wintypes as w

        class Basic(c.Structure):
            _fields_ = [('process_time', c.c_int64), ('job_time', c.c_int64), ('flags', w.DWORD),
                        ('min_working_set', c.c_size_t), ('max_working_set', c.c_size_t),
                        ('active_processes', w.DWORD), ('affinity', c.c_size_t),
                        ('priority', w.DWORD), ('scheduling', w.DWORD)]

        class Extended(c.Structure):
            _fields_ = [('basic', Basic), ('io', c.c_uint64 * 6),
                        ('process_memory', c.c_size_t), ('job_memory', c.c_size_t),
                        ('peak_process', c.c_size_t), ('peak_job', c.c_size_t)]

        kernel = c.WinDLL('kernel32', use_last_error=True)
        kernel.CreateJobObjectW.argtypes = [c.c_void_p, w.LPCWSTR]
        kernel.CreateJobObjectW.restype = w.HANDLE
        kernel.SetInformationJobObject.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD]
        kernel.SetInformationJobObject.restype = w.BOOL
        kernel.GetCurrentProcess.restype = w.HANDLE
        kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        kernel.AssignProcessToJobObject.restype = w.BOOL
        kernel.CloseHandle.argtypes = [w.HANDLE]
        job = kernel.CreateJobObjectW(None, None)
        if not job:
            raise OSError('Cannot create worker memory limit')
        info = Extended()
        info.basic.flags = 0x100 | 0x2  # PROCESS_MEMORY (commit) and PROCESS_TIME.
        info.basic.process_time = CPU_SECONDS * 10_000_000  # 100 ns units.
        info.process_memory = limit
        if (not kernel.SetInformationJobObject(job, 9, c.byref(info), c.sizeof(info))
                or not kernel.AssignProcessToJobObject(job, kernel.GetCurrentProcess())):
            kernel.CloseHandle(job)
            raise OSError('Cannot apply worker memory limit')
        global _job_handle
        _job_handle = job  # Keep the job alive until this disposable process exits.
    elif sys.platform.startswith('linux'):
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
        resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS))
    else:
        raise OSError('Unsupported worker resource limits')


def _worker_command():
    if getattr(sys, 'frozen', False):
        return [sys.executable, '--calendar-worker']
    return [sys.executable, str(Path(__file__).resolve().parents[1] / 'main.py'), '--calendar-worker']


def _run_worker(payload, *, cancelled=lambda: False, timeout=SYNC_SECONDS):
    from .mail_calendar import CalendarError, CalendarSnapshot, RemoteEvent
    if cancelled():
        raise CalendarError('Обновление отменено. Данные не изменены.')
    request = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    if len(request) > MAX_MESSAGE:
        raise CalendarError('Ответ календаря слишком большой. Данные не изменены.')
    deadline = monotonic() + timeout
    process = subprocess.Popen(_worker_command(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, creationflags=(subprocess.CREATE_NO_WINDOW
                               if sys.platform == 'win32' else 0))
    try:
        while True:
            if cancelled():
                raise CalendarError('Обновление отменено. Данные не изменены.')
            if monotonic() >= deadline:
                raise CalendarError('Превышено время обработки календаря. Данные не изменены.')
            try:
                output, _ = process.communicate(input=request, timeout=min(.05, max(.001, deadline - monotonic())))
                break
            except subprocess.TimeoutExpired:
                request = None  # communicate retains pending input across timeouts.
        if cancelled():
            raise CalendarError('Обновление отменено. Данные не изменены.')
        if process.returncode or len(output) > MAX_MESSAGE:
            raise CalendarError('Обработка календаря остановлена: превышен лимит ресурсов или ошибка процесса. Данные не изменены.')
        try:
            result = json.loads(output)
            if 'error' in result:
                raise CalendarError(result['error'])
            data = result['snapshot']
            return CalendarSnapshot(data['calendar_key'], data['start'], data['end'],
                                    tuple(RemoteEvent(**item) for item in data['events']), tuple(data['unavailable']))
        except CalendarError:
            raise
        except Exception:
            raise CalendarError('Не удалось получить результат обработки календаря. Данные не изменены.') from None
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate()  # Reap the process and close pipes after success, error or cancellation.


def fetch_snapshot_isolated(config, password, start, end, *, cancelled=lambda: False):
    return _run_worker({'operation': 'fetch', 'config': asdict(config), 'password': password,
                        'start': start.isoformat(), 'end': end.isoformat()}, cancelled=cancelled)


def parse_isolated(blobs, config, start, end, *, timeout=SYNC_SECONDS):
    """Also exercise the real worker in bundle acceptance without network access."""
    return _run_worker({'operation': 'parse', 'config': asdict(config), 'blobs': blobs,
                        'start': start.isoformat(), 'end': end.isoformat()}, timeout=timeout)


def worker_main():
    # Install OS limits before importing any parser or consuming untrusted input.
    try:
        limit_resources()
        from .mail_calendar import CalendarConfig, CalendarError, fetch_snapshot, parse_calendars
        # Windowed frozen executables may have sys.stdin/stdout=None even when
        # their native handles are explicitly redirected by the parent.
        def pipe_stream(stream, handle_id, mode):
            if stream is not None:
                return stream.buffer
            import ctypes
            import msvcrt
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.GetStdHandle.argtypes = [ctypes.c_uint32]
            kernel.GetStdHandle.restype = ctypes.c_void_p
            handle = kernel.GetStdHandle(handle_id & 0xffffffff)
            if handle in (None, ctypes.c_void_p(-1).value):
                raise OSError('Missing worker pipe')
            return os.fdopen(msvcrt.open_osfhandle(handle, os.O_BINARY), mode)

        input_stream = pipe_stream(sys.stdin, -10, 'rb')
        output = pipe_stream(sys.stdout, -11, 'wb')
        raw = input_stream.read(MAX_MESSAGE + 1)
        if len(raw) > MAX_MESSAGE:
            return 1
        request = json.loads(raw)
        config = CalendarConfig(**request['config'])
        start, end = date.fromisoformat(request['start']), date.fromisoformat(request['end'])
        # Third-party diagnostic output must never enter the result protocol.
        sys.stdout = sys.stderr if sys.stderr is not None else open(os.devnull, 'w')
        try:
            if request['operation'] == 'fetch':
                snapshot = fetch_snapshot(config, request['password'], start, end)
            elif request['operation'] == 'parse':
                snapshot = parse_calendars(request['blobs'], config, start, end)
            else:
                return 1
            result = {'snapshot': asdict(snapshot)}
        except CalendarError as exc:
            result = {'error': str(exc)}
        encoded = json.dumps(result, ensure_ascii=False).encode('utf-8')
        if len(encoded) > MAX_MESSAGE:
            return 1
        output.write(encoded)
        output.flush()
        return 0
    except BaseException:
        # Fail closed; do not expose exceptions containing calendar data or secrets.
        return 1
