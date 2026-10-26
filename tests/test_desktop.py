"""Windowless startup, installer feedback and a real Windows shortcut launch."""
import json
import os
from pathlib import Path
import subprocess
import struct
import sys
from time import monotonic, sleep

import pytest

from director_control import desktop, launcher


@pytest.mark.parametrize("use_project_venv", [True, False])
def test_source_shortcut_uses_pythonw_and_absolute_quoted_entry(tmp_path, use_project_venv):
    root = tmp_path / "Календарь директора O'Neil & команда"
    root.mkdir()
    (root / "main.pyw").write_text("", encoding="utf-8")
    executable = tmp_path / "System Python" / "python.exe"
    executable.parent.mkdir()
    target = root / ".venv" / "Scripts" / "pythonw.exe" if use_project_venv else executable.with_name("pythonw.exe")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.touch()
    spec = desktop.shortcut_spec(root, executable, frozen=False)
    assert spec.target == target.resolve()
    assert spec.arguments == (str(root.resolve() / "main.pyw"),)
    assert spec.working_directory == root.resolve()
    assert subprocess.list2cmdline(spec.arguments).startswith('"')


def test_missing_windowed_runtime_has_a_visible_installation_error(tmp_path):
    (tmp_path / "main.pyw").touch()
    with pytest.raises(RuntimeError, match="оконного запуска"):
        desktop.shortcut_spec(tmp_path, tmp_path / "python.exe", frozen=False)


def test_packaged_app_shortcut_targets_the_executable_without_python(tmp_path):
    executable = tmp_path / "Director Calendar.exe"
    spec = desktop.shortcut_spec(executable=executable, frozen=True)
    assert spec.target == executable.resolve() and spec.arguments == ()
    assert spec.working_directory == tmp_path.resolve()


def test_non_windows_creation_stops_before_windows_shell(monkeypatch):
    monkeypatch.setattr(desktop, "shortcuts_available", lambda: False)
    monkeypatch.setattr(desktop, "_save_shortcut", lambda *a: pytest.fail("Must not call Windows Shell"))
    with pytest.raises(RuntimeError, match="Windows"):
        desktop.create_desktop_shortcut()


def test_creation_failure_has_a_clear_user_message(tmp_path, monkeypatch):
    spec = desktop.ShortcutSpec(tmp_path / "pythonw.exe", (), tmp_path, tmp_path / "icon.ico")
    monkeypatch.setattr(desktop, "shortcuts_available", lambda: True)
    monkeypatch.setattr(desktop, "shortcut_spec", lambda: spec)
    def fail(*args, **kwargs):
        raise OSError("internal Windows error")
    monkeypatch.setattr(desktop, "_save_shortcut", fail)
    with pytest.raises(RuntimeError, match="доступ к рабочему столу") as error:
        desktop.create_desktop_shortcut(tmp_path)
    assert "internal Windows error" not in str(error.value)


@pytest.mark.parametrize("success", [True, False])
def test_double_click_installer_shows_success_or_failure(monkeypatch, success):
    messages = []
    monkeypatch.setattr(desktop, "show_message", lambda message, **kw: messages.append((message, kw)))
    def create():
        if not success:
            raise RuntimeError("Рабочий стол недоступен")
        return Path("Director Calendar.lnk")
    monkeypatch.setattr(desktop, "create_desktop_shortcut", create)
    assert desktop.installer_main() == (0 if success else 1)
    assert ("создан ярлык" if success else "недоступен") in messages[0][0]
    assert messages[0][1].get("error", False) is not success


def test_startup_failure_without_stderr_is_logged_and_shown(tmp_path, monkeypatch):
    from director_control import ui
    data = tmp_path / "Данные приложения"
    monkeypatch.setenv("DIRECTOR_CONTROL_DATA_DIR", str(data))
    monkeypatch.setattr(sys, "stderr", None)
    def fail():
        raise ModuleNotFoundError("Test missing dependency")
    monkeypatch.setattr(ui, "run_app", fail)
    messages = []
    monkeypatch.setattr(launcher, "show_message", lambda message, **kw: messages.append((message, kw)))
    assert launcher.main() == 1
    log = data / "startup-error.log"
    assert "Test missing dependency" in log.read_text(encoding="utf-8")
    assert str(log) in messages[0][0] and messages[0][1]["error"]


def test_settings_button_creates_shortcut_and_reports_failures(tmp_path, monkeypatch):
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication, QMessageBox
    from director_control import ui
    from director_control.storage import Store
    app = QApplication.instance() or QApplication([])
    calls, notices = [], []
    monkeypatch.setattr(ui, "shortcuts_available", lambda: True)
    monkeypatch.setattr(ui, "install_desktop_shortcut", lambda: calls.append(True))
    monkeypatch.setattr(QMessageBox, "information", lambda *args: notices.append(args[1:]))
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: notices.append(args[1:]))
    window = ui.MainWindow(Store(tmp_path / "gui.db"))
    before = window.store.audit_log()
    window.shortcut_button.click()
    assert calls == [True] and notices[0][0] == "Ярлык создан"
    def fail():
        raise RuntimeError("Нет доступа к рабочему столу")
    monkeypatch.setattr(ui, "install_desktop_shortcut", fail)
    window.shortcut_button.click()
    assert "Нет доступа" in notices[1][1]
    assert window.store.audit_log() == before
    window.close()
    window.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_app_icon_contains_small_and_large_valid_images():
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication([])
    icon = QIcon(str(desktop.app_icon_path()))
    assert not icon.isNull()
    for size in (16, 32, 48, 256):
        assert not icon.pixmap(size, size).isNull()


@pytest.mark.skipif(sys.platform != "win32", reason="Requires real Windows Shell and pythonw.exe")
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
