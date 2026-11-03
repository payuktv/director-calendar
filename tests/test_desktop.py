"""Portable shortcut specifications, installer feedback and startup errors."""
from pathlib import Path
import subprocess
import sys

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
    log = data / 'logs' / 'director-calendar.log'
    assert 'ModuleNotFoundError' in log.read_text(encoding='utf-8')
    assert 'Test missing dependency' not in log.read_text(encoding='utf-8')
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

