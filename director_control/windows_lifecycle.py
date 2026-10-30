"""Advertise the running application to the per-user Windows installer."""
import ctypes
import sys

APP_MUTEX = r'Local\DirectorCalendar.Running'
_handle = None


def hold_installer_mutex():
    global _handle
    if sys.platform != 'win32' or _handle is not None:
        return
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
    kernel.CreateMutexW.restype = wintypes.HANDLE
    _handle = kernel.CreateMutexW(None, False, APP_MUTEX)
    if not _handle:
        raise ctypes.WinError(ctypes.get_last_error())
    # Keep it until process exit, including pending Qt workers.
