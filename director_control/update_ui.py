"""Prepare a stable Windows update in the background and restart on request."""
import sys

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal
from PySide6.QtWidgets import (QApplication, QCheckBox, QDialog, QGroupBox, QHBoxLayout,
                               QPlainTextEdit, QProgressBar, QPushButton, QVBoxLayout)

from .widget_text import Message, diagnostic_message, localized, render
from .i18n import tr
from . import __version__
from .inspector import plain_label, text_label
from .package_update import WORKER_IDLE_SECONDS, install_root, packaged, pending_notes, pending_target, version_key
from .update_check import UpdateChecker, release_description


class PackagePreparer(QObject):
    prepared = Signal()
    failed = Signal(str)
    progress = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = None
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(WORKER_IDLE_SECONDS * 1000)
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
        self.timer.start()
        process.start(sys.executable, ['--prepare-update', package.version, str(package.size), package.sha256])

    def _progress(self):
        process = self.sender()
        if process is not self.process:
            return
        while process.canReadLine():
            line = bytes(process.readLine()).strip()
            if 1 <= len(line) <= 3 and line.isdigit() and int(line) <= 100:
                self.timer.start()
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
        messages = {2: tr('Пакет обновления не прошёл проверку. Попробуй проверить обновления ещё раз.'),
                    3: tr('Загрузка прервалась. Проверь подключение и попробуй снова.'),
                    4: tr('Не удалось сохранить обновление. Проверь свободное место и права на папку приложения.')}
        self.failed.emit(messages.get(code, tr('Не удалось подготовить обновление. Попробуй снова.')))

    def _error(self, error):
        if self.sender() is self.process and error == QProcess.ProcessError.FailedToStart:
            self._discard().deleteLater()
            self.failed.emit(tr('Не удалось запустить загрузку. Попробуй снова.'))

    def _timeout(self):
        self.cancel()
        self.failed.emit(tr('Истекло время подготовки обновления. Попробуй снова.'))

    def cancel(self):
        process = self._discard()
        if process is not None:
            process.kill()
            process.waitForFinished(2000)
            process.deleteLater()


class UpdateDialog(QDialog):
    """Reusable modeless release notes. Escape and the default button defer the update."""

    def __init__(self, parent):
        super().__init__(parent)
        localized(self, windowTitle='Обновление приложения')
        self.resize(520, 335)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)
        self.title = plain_label('', 'EventTitle')
        layout.addWidget(self.title)
        self.description = QPlainTextEdit()
        self.description.setReadOnly(True)
        localized(self.description, accessibleName='Описание изменений')
        layout.addWidget(self.description, 1)
        self.state = plain_label('', 'Muted')
        self.state.setWordWrap(True)
        layout.addWidget(self.state)
        actions = QHBoxLayout()
        actions.addStretch()
        self.later = localized(QPushButton(), text='Позже')
        self.later.setDefault(True)
        self.later.clicked.connect(self.reject)
        actions.addWidget(self.later)
        self.confirm = QPushButton()
        self.confirm.setObjectName('Primary')
        self.confirm.setAutoDefault(False)
        self.confirm.clicked.connect(self.accept)
        actions.addWidget(self.confirm)
        layout.addLayout(actions)


class UpdatePanel(QGroupBox):
    restart_requested = Signal()
    update_ready = Signal(str)
    indicator_changed = Signal(str)

    def __init__(self, parent=None, *, store=None, checker=None, preparer=None,
                 installed_version=__version__, supported=None):
        super().__init__(parent)
        localized(self, title='Обновления приложения')
        self.setProperty('settingsSection', True)
        self.store = store
        self.installed_version = installed_version
        version_key(installed_version)
        self.supported = packaged() if supported is None else supported
        self.release = self.ready_version = None
        self.ready_notes_body = ''
        self.download_message = ''
        self.dialog = None
        self.announced_version = None
        self.manual_check = False
        self.checker = checker if checker is not None else UpdateChecker(self)
        self.preparer = preparer if preparer is not None else PackagePreparer(self)
        self.daily = QTimer(self)
        self.daily.setInterval(24 * 60 * 60 * 1000)
        self.daily.timeout.connect(self._auto_check)
        self.startup = QTimer(self)
        self.startup.setSingleShot(True)
        self.startup.timeout.connect(self._auto_check)
        self.deferred_popup = QTimer(self)
        self.deferred_popup.setSingleShot(True)
        self.deferred_popup.timeout.connect(self.show_details)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(text_label(Message("Установленная версия: {0}", installed_version)))
        self.automatic = localized(QCheckBox(), text='Проверять обновления при запуске и раз в сутки')
        self.automatic.setChecked(self.supported and (store is None or store.get_setting('app_auto_updates', '1') == '1'))
        self.automatic.setVisible(self.supported)
        self.automatic.toggled.connect(self._preference_changed)
        layout.addWidget(self.automatic)
        self.status = text_label('Скачивание и перезапуск требуют подтверждения.' if self.supported else 'Установка обновлений доступна в сборке для Windows.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        localized(self.progress, accessibleName='Загрузка обновления')
        self.progress.hide()
        layout.addWidget(self.progress)
        row = QHBoxLayout()
        self.check_button = localized(QPushButton(), text='Проверить обновления')
        self.check_button.clicked.connect(self.check)
        row.addWidget(self.check_button)
        self.details_button = localized(QPushButton(), text='Об обновлении')
        self.details_button.clicked.connect(self.show_details)
        self.details_button.hide()
        row.addWidget(self.details_button)
        self.cancel_button = localized(QPushButton(), text='Отменить загрузку')
        self.cancel_button.clicked.connect(self._cancel_download)
        self.cancel_button.hide()
        row.addWidget(self.cancel_button)
        row.addStretch()
        layout.addLayout(row)
        self.checker.busy_changed.connect(self._refresh)
        self.checker.succeeded.connect(self._result)
        self.checker.failed.connect(self._failed)
        self.preparer.prepared.connect(self._prepared)
        self.preparer.failed.connect(self._prepare_failed)
        self.preparer.progress.connect(self.progress.setValue)

    @property
    def offered_version(self):
        if self.ready_version and (self.release is None or version_key(self.ready_version) >= version_key(self.release.version)):
            return self.ready_version
        return self.release.version if self.release else None

    def _refresh(self):
        version = self.offered_version
        self.check_button.setEnabled(not self.preparer.busy and (not self.checker.busy or self.ready_version is not None))
        self.details_button.setVisible(bool(version))
        self.cancel_button.setVisible(self.preparer.busy)
        self.progress.setVisible(self.preparer.busy)
        if not version:
            self.indicator_changed.emit('')
            if self.dialog:
                self.dialog.reject()
            return
        ready = version == self.ready_version
        if self.preparer.busy:
            hint = tr("Загружается версия {0}").format(version)
        elif ready:
            hint = tr("Версия {0} готова к установке").format(version)
        else:
            hint = tr("Доступна версия {0}").format(version)
        self.indicator_changed.emit(hint)
        if self.dialog:
            self.dialog.title.setText(hint)
            notes = self.release.notes if self.release and self.release.version == version else release_description(self.ready_notes_body)
            if self.dialog.description.toPlainText() != notes:
                self.dialog.description.setPlainText(notes)
            if ready:
                state = tr('Загрузка завершена. Для установки перезапусти календарь.')
            elif self.preparer.busy:
                state = tr('Загрузка идёт в фоне. Календарём можно пользоваться.')
            elif self.download_message:
                state = render(self.download_message)
            elif self.supported:
                state = tr("Размер загрузки: {0:.0f} МБ.").format(self.release.package.size / 2**20)
            else:
                state = tr('Установка обновлений доступна в сборке для Windows.')
            self.dialog.state.setText(state)
            action = tr('Повторить загрузку') if self.download_message else tr('Скачать обновление')
            self.dialog.confirm.setText(tr('Перезапустить и установить') if ready else action)
            self.dialog.confirm.setVisible(self.supported and not self.preparer.busy)
            self.dialog.later.setText(tr('Закрыть') if self.preparer.busy or not self.supported else tr('Позже'))

    def start_automatic(self):
        if self.supported and self._read_pending():
            self._refresh()
            localized(self.status, text=Message("Версия {0} скачана и ждёт установки.", self.ready_version))
            if self.automatic.isChecked():
                self.show_details()
        if self.automatic.isChecked():
            self.startup.start(3000)
            self.daily.start()

    def refresh_language(self):
        self._refresh()

    def _preference_changed(self, enabled):
        if self.store is not None:
            self.store.set_setting('app_auto_updates', '1' if enabled else '0')
        if enabled:
            self.startup.start(3000)
            self.daily.start()
        else:
            self.startup.stop()
            self.daily.stop()
            self.deferred_popup.stop()
            if self.checker.busy and not self.manual_check:
                self.checker.cancel()

    def _auto_check(self):
        if self.automatic.isChecked():
            self.check(manual=False)

    def check(self, *, manual=True):
        if manual and self.ready_version:
            self.show_details()
            manual = False  # A repeated check should only announce a newer offer.
        if self.checker.busy or self.preparer.busy:
            return
        self.manual_check = manual
        localized(self.status, text='Проверяем последнюю опубликованную версию…')
        self.checker.start()

    def _result(self, release):
        latest, installed = version_key(release.version), version_key(self.installed_version)
        if self.release != release:
            self.download_message = ''
        self.release = release if latest > installed else None
        self._refresh()
        version = self.offered_version
        if version:
            source = "Версия {0} скачана и ждёт установки." if self.ready_version == version else "Доступна версия {0}."
            localized(self.status, text=Message(source, version))
            if self.manual_check or version != self.announced_version:
                self.show_details()
        elif latest == installed:
            localized(self.status, text=Message("Установлена последняя опубликованная версия {0}.", self.installed_version))
        else:
            localized(self.status, text=Message("Установленная версия {0} новее последнего опубликованного выпуска {1}.",
                                                self.installed_version, release.version))

    def show_details(self):
        if not self.offered_version:
            return
        if QApplication.activeModalWidget() is not None or self.window().isMinimized():
            self.deferred_popup.start(1000)
            return
        self.deferred_popup.stop()
        if self.dialog is None:
            self.dialog = UpdateDialog(self.window())
            self.dialog.accepted.connect(self._confirmed)
        self.announced_version = self.offered_version
        self._refresh()
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()
        self.dialog.later.setFocus()

    def _confirmed(self):
        if not self.supported or self.preparer.busy or not self.offered_version:
            return
        # Keep the accepted version stable if a scheduled recheck is in flight.
        if self.checker.busy:
            self.checker.cancel()
        if self.ready_version == self.offered_version:
            self.restart_requested.emit()
            return
        package = self.release.package
        self.download_message = ''
        localized(self.status, text=Message("Загружаем и проверяем версию {0}…", package.version))
        self.progress.setValue(0)
        self.preparer.start(package)
        self._refresh()

    def _read_pending(self):
        target = pending_target(install_root(sys.executable), self.installed_version)
        self.ready_version = target.parent.name[1:] if target else None
        self.ready_notes_body = pending_notes(target) if target else ''
        return target is not None

    def _cancel_download(self):
        self.preparer.cancel()
        if self._read_pending() and self.ready_version == self.offered_version:
            self._notify_ready()
        else:
            self.download_message = 'Загрузка отменена. Можно попробовать снова.'
            self._failed(self.download_message)

    def _notify_ready(self):
        self._refresh()
        localized(self.status, text=Message("Версия {0} скачана и ждёт установки.", self.ready_version))
        self.update_ready.emit(self.ready_version)

    def _prepared(self):
        if self._read_pending():
            self._notify_ready()
        else:
            self._prepare_failed(tr('Не удалось открыть подготовленное обновление. Попробуй снова.'))

    def _prepare_failed(self, message):
        self.download_message = diagnostic_message(message)
        self._failed(message)
        if self.window().isVisible():
            self.show_details()

    def _failed(self, message):
        localized(self.status, text=diagnostic_message(message))
        self._refresh()

    def cancel(self):
        self.startup.stop()
        self.daily.stop()
        self.deferred_popup.stop()
        if self.dialog:
            self.dialog.reject()
        self.checker.cancel()
        self.preparer.cancel()
