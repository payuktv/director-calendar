"""Exercise navigation, layout and editing across settings sections."""
import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from director_control import i18n
from director_control.storage import Store
from director_control.ui import MainWindow


@pytest.fixture
def settings(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = MainWindow(Store(tmp_path / 'calendar.db'))
    window.resize(1000, 650)
    window.show()
    window.nav_buttons[3].click()
    app.processEvents()
    try:
        yield app, window
    finally:
        window.close()
        window.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        i18n.configure_widgets('ru')


def test_settings_sections_fit_and_support_keyboard_navigation(settings):
    app, window = settings
    tabs = window.settings_tabs
    section_controls = [window.language_input, window.new_category, window.mail_panel.url,
                        window.backup_panel.auto, window.diagnostics_panel]
    for index, current in enumerate(section_controls):
        if index:
            tabs.tabBar().setFocus()
            QTest.keyClick(tabs.tabBar(), Qt.Key.Key_Right)
            app.processEvents()
        assert tabs.currentIndex() == index
        assert current.isVisible()
        assert all(not other.isVisible() for other in section_controls if other is not current)
        assert tabs.currentWidget().horizontalScrollBar().maximum() == 0, tabs.tabText(index)


def test_switching_settings_keeps_drafts_and_translates_all_tabs(settings):
    app, window = settings
    tabs = window.settings_tabs
    tabs.setCurrentIndex(1)
    window.new_category.setText('Q4')
    tabs.setCurrentIndex(2)
    window.mail_panel.login.setText('draft')
    window.nav_buttons[0].click()
    window.nav_buttons[3].click()
    assert tabs.currentIndex() == 2

    tabs.setCurrentIndex(0)
    window.language_input.setCurrentIndex(window.language_input.findData('en'))
    app.processEvents()
    assert [tabs.tabText(i) for i in range(tabs.count())] == [
        'Application', 'Plan and categories', 'Mail.ru', 'Backups', 'Diagnostics']
    assert window.new_category.text() == 'Q4'
    assert window.mail_panel.login.text() == 'draft'
