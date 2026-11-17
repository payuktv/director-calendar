"""An explicit, asynchronous update check with user-controlled browser downloads."""
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QGroupBox, QHBoxLayout, QPushButton, QVBoxLayout

from . import __version__
from .diagnostics import record_error
from .inspector import plain_label
from .update_check import UpdateChecker, version_key


class UpdatePanel(QGroupBox):
    def __init__(self, parent=None, *, checker=None, installed_version=__version__):
        super().__init__('Обновления приложения', parent)
        self.setProperty('settingsSection', True)
        self.installed_version = installed_version
        version_key(installed_version)
        self.release = None
        self.checker = checker if checker is not None else UpdateChecker(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        layout.addWidget(plain_label(f'Установленная версия: {installed_version}'))
        self.status = plain_label('Проверь, доступна ли новая версия Director Calendar.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        row = QHBoxLayout()
        self.check_button = QPushButton('Проверить обновления')
        self.check_button.clicked.connect(self.check)
        row.addWidget(self.check_button)
        self.download_button = QPushButton('Скачать установщик')
        self.download_button.clicked.connect(self.open_installer)
        self.download_button.hide()
        row.addWidget(self.download_button)
        self.notes_button = QPushButton('Что нового')
        self.notes_button.clicked.connect(self.open_release_notes)
        self.notes_button.hide()
        row.addWidget(self.notes_button)
        row.addStretch()
        layout.addLayout(row)
        note = plain_label('Установщик скачивается через браузер. Перед установкой закрой календарь. '
                           'Установку запускаешь самостоятельно.', 'Muted')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.checker.busy_changed.connect(self._busy)
        self.checker.succeeded.connect(self._result)
        self.checker.failed.connect(self._failed)

    def check(self):
        if self.checker.busy:
            return
        self.release = None
        self.download_button.hide()
        self.notes_button.hide()
        self.status.setText('Проверяем последнюю опубликованную версию…')
        self.checker.start()

    def _busy(self, busy):
        self.check_button.setEnabled(not busy)

    def _result(self, release):
        self.release = release
        latest, installed = version_key(release.version), version_key(self.installed_version)
        self.notes_button.show()
        if latest > installed:
            self.status.setText(f'Доступна новая версия {release.version}. Установлена {self.installed_version}.')
            self.download_button.setText(f'Скачать версию {release.version}')
            self.download_button.show()
        elif latest == installed:
            self.status.setText(f'Установлена последняя опубликованная версия {self.installed_version}.')
        else:
            self.status.setText(f'Установленная версия {self.installed_version} новее последнего '
                                f'опубликованного выпуска {release.version}.')

    def _failed(self, message):
        self.release = None
        self.download_button.hide()
        self.notes_button.hide()
        self.status.setText(message)

    def _open(self, installer):
        if self.release is None:
            return
        url = self.release.installer_url if installer else self.release.page_url
        try:
            if not QDesktopServices.openUrl(QUrl(url)):
                raise OSError('Browser could not be opened')
        except Exception as exc:
            record_error('ui.action', exc)
            self.status.setText('Не удалось открыть браузер. Проверь браузер по умолчанию и попробуй снова.')

    def open_installer(self):
        self._open(True)

    def open_release_notes(self):
        self._open(False)

    def cancel(self):
        self.checker.cancel()
