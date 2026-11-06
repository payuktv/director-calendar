from pathlib import Path
from time import monotonic, sleep

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from director_control import backups
from director_control.storage import Store
from director_control.ui import MainWindow


def settle(app, panel):
    deadline = monotonic()+5
    while panel.busy and monotonic() < deadline:
        app.processEvents()
        # Release Python's GIL so this polling loop cannot starve BackupWorker.
        sleep(.01)
    assert not panel.busy


def make_window(tmp_path):
    app = QApplication.instance() or QApplication([])
    store = Store(tmp_path / 'gui.db')
    eid = store.create_event('Исходное событие', 'Работа', actual_start='2026-10-26T11:00:00', actual_end='2026-10-26T11:30:00')
    window = MainWindow(store)
    return app, store, eid, window


def test_backup_settings_and_manual_copy_use_selected_folder(tmp_path, monkeypatch):
    app, store, eid, window = make_window(tmp_path)
    panel = window.backup_panel
    panel.auto.setChecked(False)
    folder = tmp_path / 'Копии календаря'
    panel.folder.setText(str(folder))
    panel.keep.setValue(5)
    panel.save_button.click()
    assert store.get_setting('backup_auto') == '0'
    assert store.get_setting('backup_keep') == '5'
    messages = []
    monkeypatch.setattr(QMessageBox, 'information', lambda *args: messages.append(args[2]))
    panel.manual_button.click()
    settle(app, panel)
    assert len(list(folder.glob('backup-*.db'))) == 1
    assert messages and Path(messages[-1]).is_file()
    assert store.get_event(eid).title == 'Исходное событие'
    window.close()


def test_restore_waits_for_mail_requires_confirmation_and_closes_the_old_window(tmp_path, monkeypatch):
    app, store, eid, window = make_window(tmp_path)
    panel = window.backup_panel
    source = backups.create_backup(store)
    store.update_event(eid, title='Новые данные')
    information = []
    monkeypatch.setattr(QMessageBox, 'information', lambda *args: information.append(args[2]))
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *args: (str(source), ''))
    window.mail_panel.worker = object()
    panel.restore_button.click()
    assert not panel.busy and information
    window.mail_panel.worker = None
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.No)
    panel.restore_button.click()
    assert store.get_event(eid).title == 'Новые данные'
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Yes)
    panel.restore_button.click()
    assert panel.restoring and not window.isEnabled()
    settle(app, panel)
    assert store.get_event(eid).title == 'Исходное событие'
    assert window._restored and not window.isVisible()
    assert any('Страховая копия' in text for text in information)


def test_automatic_backup_failure_is_visible_and_does_not_hang_the_app(tmp_path, monkeypatch):
    app, store, eid, window = make_window(tmp_path)
    def fail(*args, **kwargs):
        raise OSError('Папка копий недоступна')
    monkeypatch.setattr(backups, 'create_backup', fail)
    window.backup_panel.check()
    settle(app, window.backup_panel)
    assert 'недоступна' in window.mail_status.text()
    assert store.get_event(eid).title == 'Исходное событие'
    assert window.backup_panel.manual_button.isEnabled()
    window.close()
