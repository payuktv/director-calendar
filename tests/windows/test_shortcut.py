"""Native Windows Shell integration; collected only by the Windows suite."""
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
from time import monotonic, sleep

import pytest

from director_control import desktop


def test_windows_shortcut_launches_real_window_without_console_from_unicode_path(tmp_path, monkeypatch):
    root = tmp_path / "Календарь директора O'Neil & команда"
    root.mkdir()
    data = root / "Локальные данные"
    monkeypatch.setenv("DIRECTOR_CONTROL_DATA_DIR", str(data))
    ready, pid_file = root / "ready.json", root / "pid.txt"
    entry = root / "main.pyw"
    # Launch the real GUI in another process; only this test subclass closes it.
    entry.write_text(f'''
import ctypes, json, os, sys
from pathlib import Path
Path({str(pid_file)!r}).write_text(str(os.getpid()))
from PySide6.QtCore import QTimer
from director_control import ui
from director_control.launcher import main
Original = ui.MainWindow
class ProbeWindow(Original):
    def show(self):
        super().show()
        QTimer.singleShot(100, self.record)
    def record(self):
        pending = Path({str(ready.with_suffix('.tmp'))!r})
        pending.write_text(json.dumps({{
            "cwd": os.getcwd(), "argv": sys.argv, "executable": sys.executable,
            "console": bool(ctypes.windll.kernel32.GetConsoleWindow()),
            "stdout_none": sys.stdout is None, "visible": self.isVisible(),
            "database": str(self.store.path), "icon": not self.windowIcon().isNull(),
        }}), encoding="utf-8")
        pending.replace(Path({str(ready)!r}))
        self.close()
ui.MainWindow = ProbeWindow
raise SystemExit(main())
''', encoding="utf-8")
    spec = desktop.shortcut_spec(root, Path(sys.executable), frozen=False)
    monkeypatch.setattr(desktop, "shortcut_spec", lambda: spec)
    desktop_dir = tmp_path / "Рабочий стол"
    desktop_dir.mkdir()
    try:
        shortcut = desktop.create_desktop_shortcut(desktop_dir)
    except RuntimeError as exc:
        pytest.fail(str(exc.__cause__) or str(exc))
    assert desktop.create_desktop_shortcut(desktop_dir) == shortcut
    assert list(desktop_dir.iterdir()) == [shortcut]
    # Read StringData independently using Microsoft's MS-SHLLINK file format.
    # https://learn.microsoft.com/openspecs/windows_protocols/ms-shllink/17b69472-0f34-4bcf-b290-eccdb8de224b
    blob = shortcut.read_bytes()
    assert struct.unpack_from("<I", blob)[0] == 0x4C
    flags = struct.unpack_from("<I", blob, 20)[0]
    assert flags & 0x80  # IsUnicode
    offset = 76
    if flags & 1:
        offset += 2 + struct.unpack_from("<H", blob, offset)[0]
    if flags & 2:
        offset += struct.unpack_from("<I", blob, offset)[0]
    saved = {}
    for flag, key in ((4, "name"), (8, "relative"), (16, "cwd"), (32, "arguments"), (64, "icon")):
        if flags & flag:
            count = struct.unpack_from("<H", blob, offset)[0]
            offset += 2
            saved[key] = blob[offset:offset + count * 2].decode("utf-16-le")
            offset += count * 2
    assert saved["arguments"] == subprocess.list2cmdline(spec.arguments)
    assert Path(saved["cwd"]) == root
    assert Path(saved["icon"]) == spec.icon
    assert struct.unpack_from("<I", blob, 56)[0] == 0  # IconIndex
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                        r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as key:
        expected_desktop = winreg.QueryValueEx(key, "Desktop")[0]
    assert desktop.desktop_directory() == Path(os.path.expandvars(expected_desktop))
    try:
        os.startfile(str(shortcut))
        deadline = monotonic() + 25
        while not ready.is_file() and monotonic() < deadline:
            sleep(.05)
        assert ready.is_file(), (data / "startup-error.log").read_text(encoding="utf-8") if (data / "startup-error.log").is_file() else "Window did not open"
        result = json.loads(ready.read_text(encoding="utf-8"))
        assert Path(result["cwd"]) == root and result["argv"] == [str(entry)]
        assert Path(result["executable"]) == spec.target
        assert not result["console"] and result["stdout_none"] and result["visible"] and result["icon"]
        assert Path(result["database"]) == data / "director_control.db"
    finally:
        if pid_file.is_file():
            pid = int(pid_file.read_text())
            # Only the child created by this test; no other pythonw processes.
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
