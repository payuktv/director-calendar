"""GUI smoke test runs with the offscreen Qt platform on CI."""
import os

import pytest


def test_main_window_can_be_created(tmp_path, monkeypatch):
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from director_control.storage import Store
    from director_control.ui import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow(Store(tmp_path / "gui.db"))
    assert window.tabs.count() == 4
    assert window.table.rowCount() == 0
    window.close()
