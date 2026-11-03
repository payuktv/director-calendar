"""Backup settings and non-blocking snapshot/restore operations."""
import json

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLineEdit,
    QMessageBox, QPushButton, QSpinBox, QVBoxLayout,
)

from .backups import backup_folder, create_backup, restore_backup, save_backup_settings, scheduled_backup
from .inspector import plain_label
from .diagnostics import record_error


class BackupWorker(QThread):
    def __init__(self, store, action, source=None, parent=None):
        super().__init__(parent)
        self.store, self.action, self.source = store, action, source
        self.result, self.error = None, ''

    def run(self):
        try:
            if self.action == 'restore':
                self.result = restore_backup(self.store, self.source)
            elif self.action == 'manual':
                self.result = create_backup(self.store, backup_folder(self.store))
            else:
                self.result = scheduled_backup(self.store)
        except Exception as exc:
            record_error({'restore': 'backup.restore', 'manual': 'backup.manual'}.get(self.action, 'backup.auto'), exc)
            self.error = str(exc)


class BackupPanel(QGroupBox):
    notice = Signal(str)
    restored = Signal(str)

    def __init__(self, store, can_restore, parent=None):
        super().__init__('Данные и резервные копии', parent)
        self.setProperty('settingsSection', True)
        self.store, self.can_restore = store, can_restore
        self.worker = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        path = plain_label('База данных: ' + str(store.path))
        path.setWordWrap(True)
        layout.addWidget(path)
        form = QFormLayout()
        form.setHorizontalSpacing(24)
        form.setVerticalSpacing(14)
        self.auto = QCheckBox('Создавать копию каждый день при работе приложения')
        self.auto.setChecked(store.get_setting('backup_auto', '1') == '1')
        form.addRow('', self.auto)
        folder_row = QHBoxLayout()
        folder_row.setSpacing(12)
        self.folder = QLineEdit(store.get_setting('backup_folder'))
        self.folder.setPlaceholderText(str(store.path.parent / 'backups'))
        folder_row.addWidget(self.folder)
        self.choose_button = QPushButton('Выбрать папку')
        self.choose_button.clicked.connect(self.choose_folder)
        folder_row.addWidget(self.choose_button)
        form.addRow('Папка копий', folder_row)
        self.keep = QSpinBox()
        self.keep.setRange(1, 365)
        self.keep.setValue(int(store.get_setting('backup_keep', '30')))
        self.keep.setMaximumWidth(160)
        form.addRow('Хранить автоматических копий', self.keep)
        layout.addLayout(form)
        note = plain_label('По умолчанию храним 30 ежедневных копий. Ручные копии и копии перед восстановлением не удаляются автоматически. '
                           'Можно выбрать папку на другом диске.', 'Muted')
        note.setWordWrap(True)
        layout.addWidget(note)
        actions = QHBoxLayout()
        actions.setSpacing(12)
        self.save_button = QPushButton('Сохранить настройки копий')
        self.save_button.clicked.connect(self.save_settings)
        actions.addWidget(self.save_button)
        actions.addStretch()
        layout.addLayout(actions)
        operations = QHBoxLayout()
        operations.setSpacing(12)
        self.manual_button = QPushButton('Создать резервную копию')
        self.manual_button.clicked.connect(self.make_manual)
        operations.addWidget(self.manual_button)
        self.restore_button = QPushButton('Восстановить из копии…')
        self.restore_button.clicked.connect(self.restore)
        operations.addWidget(self.restore_button)
        operations.addStretch()
        layout.addLayout(operations)
        self.status = plain_label('', 'Muted')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.timer = QTimer(self)
        self.timer.setInterval(15 * 60 * 1000)
        self.timer.timeout.connect(self.check)
        self.refresh()

    @property
    def busy(self):
        return self.worker is not None

    @property
    def restoring(self):
        return self.busy and self.worker.action == 'restore'

    def refresh(self):
        try:
            last = json.loads(self.store.get_setting('backup_last_auto', '{}'))
        except (TypeError, ValueError):
            last = {}
        if not isinstance(last, dict):
            last = {}
        self.status.setText('Последняя автоматическая копия: ' + (last.get('day') or 'ещё не создана'))

    def start(self):
        self.timer.start()
        self.check()

    def check(self):
        if not self.busy and self.store.get_setting('backup_auto', '1') == '1':
            self._start('auto')

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, 'Папка резервных копий', str(backup_folder(self.store)))
        if folder:
            self.folder.setText(folder)

    def save_settings(self):
        try:
            save_backup_settings(self.store, self.auto.isChecked(), self.folder.text().strip(), self.keep.value())
            self.status.setText('Настройки копирования сохранены.')
            self.check()
        except Exception as exc:
            record_error('backup.settings', exc)
            QMessageBox.warning(self, 'Резервные копии', str(exc))

    def make_manual(self):
        self._start('manual')

    def restore(self):
        if self.busy or not self.can_restore():
            QMessageBox.information(self, 'Восстановление базы', 'Дождись завершения обновления Mail.ru и копирования данных.')
            return
        source, _ = QFileDialog.getOpenFileName(self, 'Выбрать резервную копию', str(backup_folder(self.store)), 'Базы данных (*.db *.sqlite);;Все файлы (*)')
        if not source:
            return
        answer = QMessageBox.question(self, 'Восстановить базу данных?',
            'Текущие события, история и настройки будут заменены данными из выбранной копии. '
            'Перед заменой сохраним отдельную копию текущей базы. После успешного восстановления приложение закроется; открой его снова.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            self._start('restore', source)

    def _start(self, action, source=None):
        if self.busy:
            return
        if action == 'restore' and not self.can_restore():
            QMessageBox.information(self, 'Восстановление базы', 'Началось обновление Mail.ru. Дождись его завершения.')
            return
        for control in (self.auto, self.folder, self.keep, self.choose_button, self.save_button, self.manual_button, self.restore_button):
            control.setEnabled(False)
        if action == 'restore':
            self.window().setEnabled(False)
        self.status.setText('Восстанавливаем базу…' if action == 'restore' else 'Проверяем и сохраняем резервную копию…')
        self.worker = BackupWorker(self.store, action, source, self)
        self.worker.finished.connect(self._finished)
        self.worker.start()

    def _finished(self):
        worker, self.worker = self.worker, None
        action, result, error = worker.action, worker.result, worker.error
        worker.deleteLater()
        if action == 'restore':
            self.window().setEnabled(True)
        for control in (self.auto, self.folder, self.keep, self.choose_button, self.save_button, self.manual_button, self.restore_button):
            control.setEnabled(True)
        if error:
            self.status.setText('Операция не завершена: ' + error)
            self.notice.emit(self.status.text())
            if action != 'auto':
                QMessageBox.warning(self, 'Резервные копии', error)
        elif action == 'restore':
            self.timer.stop()
            QMessageBox.information(self, 'База восстановлена', 'Данные восстановлены. Открой приложение снова.\nСтраховая копия прежних данных:\n' + str(result))
            self.restored.emit(str(result))
        elif action == 'manual':
            self.status.setText('Копия создана: ' + str(result))
            QMessageBox.information(self, 'Резервная копия создана', str(result))
        else:
            self.refresh()

