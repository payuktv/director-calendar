"""Windows desktop shortcuts. No Qt or additional installation dependencies."""
from __future__ import annotations

import base64
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
from dataclasses import dataclass


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
    icon = app_icon_path()
    return ShortcutSpec(target, arguments, working_directory, icon if icon.is_file() else target)


def _shortcut_command(spec: ShortcutSpec, desktop_dir: Path | None) -> list[str]:
    # Paths travel as data, including quotes, Cyrillic letters and shell symbols.
    payload = base64.b64encode(json.dumps({
        "target": str(spec.target), "arguments": subprocess.list2cmdline(spec.arguments),
        "working_directory": str(spec.working_directory), "icon": str(spec.icon),
        "desktop": str(desktop_dir.resolve()) if desktop_dir is not None else None,
    }, ensure_ascii=False).encode("utf-8")).decode("ascii")
    script = """
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$spec = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('__PAYLOAD__')) | ConvertFrom-Json
$shell = New-Object -ComObject WScript.Shell
$desktop = $spec.desktop
if ([String]::IsNullOrWhiteSpace($desktop)) { $desktop = $shell.SpecialFolders.Item('Desktop') }
if ([String]::IsNullOrWhiteSpace($desktop) -or -not [IO.Directory]::Exists($desktop)) {
    throw 'Desktop directory is unavailable.'
}
$path = [IO.Path]::Combine($desktop, 'Director Calendar.lnk')
$link = $shell.CreateShortcut($path)
$link.TargetPath = $spec.target
$link.Arguments = $spec.arguments
$link.WorkingDirectory = $spec.working_directory
$link.IconLocation = $spec.icon + ',0'
$link.Description = 'Director Calendar'
$link.WindowStyle = 1
$link.Save()
[Console]::WriteLine($path)
""".replace("__PAYLOAD__", payload)
    powershell = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    return [str(powershell), "-NoProfile", "-NonInteractive", "-EncodedCommand",
            base64.b64encode(script.encode("utf-16-le")).decode("ascii")]


def create_desktop_shortcut(desktop_dir: Path | None = None) -> Path:
    if not shortcuts_available():
        raise RuntimeError("Создание ярлыка на рабочем столе доступно в Windows.")
    spec = shortcut_spec()
    try:
        result = subprocess.run(_shortcut_command(spec, desktop_dir), check=True, capture_output=True,
                                encoding="utf-8", timeout=20, creationflags=0x08000000)  # CREATE_NO_WINDOW
        path = Path(result.stdout.strip())
        if path.name != "Director Calendar.lnk" or not path.is_file():
            raise OSError("Shortcut was not saved.")
        return path
    except (OSError, subprocess.SubprocessError) as exc:
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
