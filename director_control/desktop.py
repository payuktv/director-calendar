"""Windows desktop shortcuts. No Qt or additional installation dependencies."""
from __future__ import annotations

import ctypes
from pathlib import Path
import subprocess
import sys
from dataclasses import dataclass
from contextlib import contextmanager
from uuid import UUID


def shortcuts_available() -> bool:
    return sys.platform == "win32"


def app_icon_path() -> Path:
    return Path(__file__).resolve().parent / "assets" / "director-calendar.ico"


@dataclass(frozen=True)
class ShortcutSpec:
    target: Path
    arguments: tuple[str, ...]
    working_directory: Path
    icon: Path


def shortcut_spec(root: Path | None = None, executable: Path | None = None,
                  frozen: bool | None = None) -> ShortcutSpec:
    executable = Path(executable or sys.executable).resolve()
    if frozen is None:
        frozen = bool(getattr(sys, "frozen", False) or "__compiled__" in globals())
    if frozen:
        from .package_update import install_root
        base = install_root(executable)
        if base != executable.parent:
            executable = base / executable.name
        target, arguments, working_directory = executable, (), executable.parent
    else:
        root = (root or Path(__file__).resolve().parent.parent).resolve()
        entry = root / "main.pyw"
        # The installer may be opened by the system Python file association.
        # Always prefer the project's already installed environment in that case.
        target = root / ".venv" / "Scripts" / "pythonw.exe"
        if not target.is_file():
            target = executable.with_name("pythonw.exe")
        if not entry.is_file() or not target.is_file():
            raise RuntimeError("Не найден компонент оконного запуска. Повтори установку приложения и создай ярлык снова.")
        arguments, working_directory = (str(entry),), root
    icon = target if frozen else app_icon_path()
    return ShortcutSpec(target, arguments, working_directory, icon if icon.is_file() else target)


class _GUID(ctypes.Structure):
    _fields_ = [("data1", ctypes.c_uint32), ("data2", ctypes.c_uint16),
                ("data3", ctypes.c_uint16), ("data4", ctypes.c_ubyte * 8)]

    @classmethod
    def parse(cls, value):
        return cls.from_buffer_copy(UUID(value).bytes_le)


_CLSID_SHELL_LINK = _GUID.parse("00021401-0000-0000-C000-000000000046")
_IID_SHELL_LINK_W = _GUID.parse("000214F9-0000-0000-C000-000000000046")
_IID_PERSIST_FILE = _GUID.parse("0000010B-0000-0000-C000-000000000046")
_FOLDERID_DESKTOP = _GUID.parse("B4BFCC3A-DB2C-424C-B029-7FE99A87C641")


def _check_hresult(result):
    if result < 0:
        raise OSError(f"Windows Shell error 0x{result & 0xFFFFFFFF:08X}")


@contextmanager
def _com_runtime():
    ole = ctypes.WinDLL("ole32")
    ole.CoInitializeEx.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
    ole.CoInitializeEx.restype = ctypes.c_long
    ole.CoUninitialize.argtypes = ()
    ole.CoUninitialize.restype = None
    ole.CoTaskMemFree.argtypes = (ctypes.c_void_p,)
    ole.CoTaskMemFree.restype = None
    ole.CoCreateInstance.argtypes = (ctypes.POINTER(_GUID), ctypes.c_void_p, ctypes.c_uint32,
                                    ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p))
    ole.CoCreateInstance.restype = ctypes.c_long
    result = ole.CoInitializeEx(None, 2)  # COINIT_APARTMENTTHREADED
    # Qt may have initialized this thread already with a different apartment.
    if result < 0 and result & 0xFFFFFFFF != 0x80010106:  # RPC_E_CHANGED_MODE
        _check_hresult(result)
    try:
        yield ole
    finally:
        if result >= 0:
            ole.CoUninitialize()


def desktop_directory() -> Path:
    """Ask Windows for the user's current Desktop, including folder redirection."""
    with _com_runtime() as ole:
        shell = ctypes.WinDLL("shell32")
        get_path = shell.SHGetKnownFolderPath
        get_path.argtypes = (ctypes.POINTER(_GUID), ctypes.c_uint32, ctypes.c_void_p,
                             ctypes.POINTER(ctypes.c_wchar_p))
        get_path.restype = ctypes.c_long
        path = ctypes.c_wchar_p()
        try:
            _check_hresult(get_path(ctypes.byref(_FOLDERID_DESKTOP), 0, None, ctypes.byref(path)))
            if not path.value:
                raise OSError("Windows returned an empty Desktop path.")
            return Path(path.value)
        finally:
            ole.CoTaskMemFree(ctypes.cast(path, ctypes.c_void_p))


def _com_method(interface, slot, result_type, *argument_types):
    table = ctypes.cast(interface, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    function = ctypes.WINFUNCTYPE(result_type, ctypes.c_void_p, *argument_types)(table[slot])
    return lambda *args: function(interface, *args)


def _save_shortcut(spec: ShortcutSpec, path: Path) -> None:
    # IShellLinkW / IPersistFile method order follows the Windows SDK interfaces:
    # https://learn.microsoft.com/windows/win32/api/shobjidl_core/nn-shobjidl_core-ishelllinkw
    # Wide-character setters and Save avoid WScript.Shell's ANSI path conversion.
    with _com_runtime() as ole:
        link, persist = ctypes.c_void_p(), ctypes.c_void_p()
        try:
            _check_hresult(ole.CoCreateInstance(ctypes.byref(_CLSID_SHELL_LINK), None, 1,
                           ctypes.byref(_IID_SHELL_LINK_W), ctypes.byref(link)))
            def call(slot, types, *args):
                _check_hresult(_com_method(link, slot, ctypes.c_long, *types)(*args))
            call(20, (ctypes.c_wchar_p,), str(spec.target))  # SetPath
            call(7, (ctypes.c_wchar_p,), "Director Calendar")  # SetDescription
            call(9, (ctypes.c_wchar_p,), str(spec.working_directory))  # SetWorkingDirectory
            call(11, (ctypes.c_wchar_p,), subprocess.list2cmdline(spec.arguments))  # SetArguments
            call(15, (ctypes.c_int,), 1)  # SetShowCmd: SW_SHOWNORMAL
            call(17, (ctypes.c_wchar_p, ctypes.c_int), str(spec.icon), 0)  # SetIconLocation
            call(0, (ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p)),
                 ctypes.byref(_IID_PERSIST_FILE), ctypes.byref(persist))  # QueryInterface
            save = _com_method(persist, 6, ctypes.c_long, ctypes.c_wchar_p, ctypes.c_int)
            _check_hresult(save(str(path), 1))  # IPersistFile::Save
        finally:
            if persist.value:
                _com_method(persist, 2, ctypes.c_ulong)()  # IUnknown::Release
            if link.value:
                _com_method(link, 2, ctypes.c_ulong)()


def create_desktop_shortcut(desktop_dir: Path | None = None) -> Path:
    if not shortcuts_available():
        raise RuntimeError("Создание ярлыка на рабочем столе доступно в Windows.")
    spec = shortcut_spec()
    try:
        directory = desktop_dir.resolve() if desktop_dir is not None else desktop_directory()
        if not directory.is_dir():
            raise OSError("Desktop directory is unavailable.")
        path = directory / "Director Calendar.lnk"
        _save_shortcut(spec, path)
        if not path.is_file():
            raise OSError("Shortcut was not saved.")
        return path
    except (OSError, ValueError) as exc:
        raise RuntimeError("Не удалось создать ярлык. Проверь доступ к рабочему столу и повтори.") from exc


def show_message(message: str, *, error: bool = False) -> None:
    if shortcuts_available():
        from ctypes import wintypes
        message_box = ctypes.WinDLL("user32", use_last_error=True).MessageBoxW
        message_box.argtypes = (wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.UINT)
        message_box.restype = ctypes.c_int
        message_box(None, message, "Director Calendar", 0x10 if error else 0x40)
    elif sys.stderr is not None:
        print(message, file=sys.stderr)


def installer_main() -> int:
    try:
        create_desktop_shortcut()
    except Exception as exc:
        show_message(str(exc), error=True)
        return 1
    show_message("На рабочем столе создан ярлык «Director Calendar».\n\nОткрывай календарь двойным щелчком по нему.")
    return 0
