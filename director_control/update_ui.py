"""Prepare a stable Windows update in the background and restart on request."""
import sys

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QCheckBox, QGroupBox, QHBoxLayout, QProgressBar, QPushButton, QVBoxLayout

from . import __version__
from .diagnostics import record_error
from .inspector import plain_label
from .package_update import MAX_SECONDS, install_root, packaged, ready_target, version_key
from .update_check import UpdateChecker


class PackagePreparer(QObject):
    prepared = Signal()
    failed = Signal(str)
    progress = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = None
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._timeout)

    @property
    def busy(self):
        return self.process is not None

    def start(self, package):
        if self.busy:
            return
        process = QProcess(self)
        self.process = process
        process.finished.connect(self._finished)
        process.errorOccurred.connect(self._error)
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert('PYINSTALLER_RESET_ENVIRONMENT', '1')
        process.setProcessEnvironment(environment)
        process.readyReadStandardOutput.connect(self._progress)
        process.setStandardErrorFile(QProcess.nullDevice())
        self.timer.start((MAX_SECONDS + 60) * 1000)
        process.start(sys.executable, ['--prepare-update', package.version, str(package.size), package.sha256])

    def _progress(self):
        process = self.sender()
        if process is not self.process:
            return
        while process.canReadLine():
            line = bytes(process.readLine()).strip()
            if 1 <= len(line) <= 3 and line.isdigit() and int(line) <= 100:
                self.progress.emit(int(line))

    def _discard(self):
        process, self.process = self.process, None
        self.timer.stop()
        return process

    def _finished(self, code, status):
        if self.sender() is not self.process:
            return
        self._discard().deleteLater()
        if code == 0 and status == QProcess.ExitStatus.NormalExit:
            self.prepared.emit()
            return
        messages = {2: 'Пакет обновления не прошёл проверку. Попробуй проверить обновления ещё раз.',
                    3: 'Загрузка прервалась. Проверь подключение и попробуй снова.',
                    4: 'Не удалось сохранить обновление. Проверь свободное место и права на папку приложения.'}
        self.failed.emit(messages.get(code, 'Не удалось подготовить обновление. Попробуй снова.'))

    def _error(self, error):
        if self.sender() is self.process and error == QProcess.ProcessError.FailedToStart:
            self._discard().deleteLater()
            self.failed.emit('Не удалось запустить загрузку. Попробуй снова.')

    def _timeout(self):
        self.cancel()
        self.failed.emit('Истекло время подготовки обновления. Попробуй снова.')

    def cancel(self):
        process = self._discard()
        if process is not None:
            process.kill()
            process.waitForFinished(2000)
            process.deleteLater()


class UpdatePanel(QGroupBox):
    restart_requested = Signal()
    update_ready = Signal(str)

    def __init__(self, parent=None, *, store=None, checker=None, preparer=None,
                 installed_version=__version__, supported=None):
        super().__init__('Обновления приложения', parent)
        self.setProperty('settingsSection', True)
        self.store = store
        self.installed_version = installed_version
        version_key(installed_version)
        self.supported = packaged() if supported is None else supported
        self.release = self.ready_version = None
        self.checker = checker if checker is not None else UpdateChecker(self)
        self.preparer = preparer if preparer is not None else PackagePreparer(self)
        self.daily = QTimer(self)
        self.daily.setInterval(24 * 60 * 60 * 1000)
        self.daily.timeout.connect(self._auto_check)
        self.startup = QTimer(self)
        self.startup.setSingleShot(True)
        self.startup.timeout.connect(self._auto_check)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        layout.addWidget(plain_label(f'Установленная версия: {installed_version}'))
        self.automatic = QCheckBox('Автоматически загружать обновления')
        self.automatic.setChecked(self.supported and (store is None or store.get_setting('app_auto_updates', '1') == '1'))
        self.automatic.setVisible(self.supported)
        self.automatic.toggled.connect(self._preference_changed)
        layout.addWidget(self.automatic)
        self.status = plain_label('Готовое обновление применится при следующем запуске.' if self.supported
                                  else 'Автообновление доступно в сборке для Windows.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setAccessibleName('Загрузка обновления')
        self.progress.hide()
        layout.addWidget(self.progress)
        row = QHBoxLayout()
        self.check_button = QPushButton('Проверить обновления')
        self.check_button.clicked.connect(self.check)
        row.addWidget(self.check_button)
        self.download_button = QPushButton('Обновить')
        self.download_button.clicked.connect(self._action)
        self.download_button.hide()
        row.addWidget(self.download_button)
        self.notes_button = QPushButton('Что нового')
        self.notes_button.clicked.connect(self.open_release_notes)
        self.notes_button.hide()
        row.addWidget(self.notes_button)
        row.addStretch()
        layout.addLayout(row)
        self.checker.busy_changed.connect(self._busy)
        self.checker.succeeded.connect(self._result)
        self.checker.failed.connect(self._failed)
        self.preparer.prepared.connect(self._prepared)
        self.preparer.failed.connect(self._prepare_failed)
        self.preparer.progress.connect(self.progress.setValue)

    def start_automatic(self):
        if self.supported and self.automatic.isChecked():
            self.startup.start(3000)
            self.daily.start()

    def _preference_changed(self, enabled):
        if self.store is not None:
            self.store.set_setting('app_auto_updates', '1' if enabled else '0')
        if enabled:
            self.start_automatic()
        else:
            self.startup.stop()
            self.daily.stop()
            if self.preparer.busy:
                self._cancel_download()

    def _auto_check(self):
        if self.automatic.isChecked():
            self.check()

    def check(self):
        if self.checker.busy or self.preparer.busy or self.ready_version:
            return
        self.release = None
        self.download_button.hide()
        self.notes_button.hide()
        self.status.setText('Проверяем последнюю опубликованную версию…')
        self.checker.start()

    def _busy(self, busy):
        self.check_button.setEnabled(not busy and not self.preparer.busy and not self.ready_version)

    def _result(self, release):
        self.release = release
        latest, installed = version_key(release.version), version_key(self.installed_version)
        self.notes_button.show()
        if latest > installed:
            self.status.setText(f'Доступна версия {release.version}.')
            if self.supported:
                self.download_button.setText(f'Обновить до {release.version}')
                self.download_button.show()
                if self.automatic.isChecked():
                    self._download()
        elif latest == installed:
            self.status.setText(f'Установлена последняя опубликованная версия {self.installed_version}.')
        else:
            self.status.setText(f'Установленная версия {self.installed_version} новее последнего '
                                f'опубликованного выпуска {release.version}.')

    def _action(self):
        if self.preparer.busy:
            self._cancel_download()
        elif self.ready_version:
            self.restart_requested.emit()
        else:
            self._download()

    def _download(self):
        if not self.supported or self.release is None or self.preparer.busy:
            return
        package = self.release.package
        self.status.setText(f'Загружаем и проверяем версию {package.version} ({package.size / 2**20:.0f} МБ)…')
        self.check_button.setEnabled(False)
        self.download_button.setText('Отменить загрузку')
        self.progress.setValue(0)
        self.progress.show()
        self.preparer.start(package)

    def _cancel_download(self):
        self.preparer.cancel()
        # The worker could have committed immediately before receiving cancel.
        if self._show_ready():
            return
        self._prepare_failed('Загрузка отменена.')

    def _show_ready(self):
        target = ready_target(install_root(sys.executable), self.installed_version) if self.supported else None
        if target is None:
            return False
        self.ready_version = target.parent.name[1:]
        self.progress.hide()
        self.status.setText(f'Версия {self.ready_version} готова. Она откроется при следующем запуске.')
        self.download_button.setText('Перезапустить сейчас')
        self.download_button.show()
        self.check_button.setEnabled(False)
        self.update_ready.emit(self.ready_version)
        return True

    def _prepared(self):
        if not self._show_ready():
            self._prepare_failed('Не удалось открыть подготовленное обновление. Попробуй снова.')

    def _prepare_failed(self, message):
        self.progress.hide()
        self.check_button.setEnabled(True)
        self.download_button.setText('Повторить загрузку')
        self.status.setText(message)

    def _failed(self, message):
        self.release = None
        self.download_button.hide()
        self.notes_button.hide()
        self.status.setText(message)

    def open_release_notes(self):
        if self.release is None:
            return
        try:
            if not QDesktopServices.openUrl(QUrl(self.release.page_url)):
                raise OSError('Browser could not be opened')
        except Exception as exc:
            record_error('ui.action', exc)
            self.status.setText('Не удалось открыть описание выпуска в браузере.')

    def cancel(self):
        self.startup.stop()
        self.daily.stop()
        self.checker.cancel()
        self.preparer.cancel()
