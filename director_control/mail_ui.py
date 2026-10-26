"""Connection panel and background read-only synchronization."""
from datetime import date

from PySide6.QtCore import QThread, QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from .credentials import Credentials
from .mail_calendar import CalendarConfig, CalendarError, fetch_snapshot, window_for_day


class SyncThread(QThread):
    snapshot_ready = Signal(object)
    failed = Signal(str)

    def __init__(self, config, password, day, parent=None):
        super().__init__(parent)
        self.config = config
        self.password = password
        self.day = day

    def run(self):
        try:
            self.snapshot_ready.emit(fetch_snapshot(self.config, self.password, *window_for_day(self.day)))
        except CalendarError as exc:
            self.failed.emit(str(exc))
        except Exception:
            self.failed.emit("Не удалось обновить календарь. Локальные данные сохранены.")
        finally:
            self.password = ""


class MailPanel(QGroupBox):
    changed = Signal()
    message = Signal(str)
    busy_changed = Signal(bool)

    def __init__(self, store, selected_day, parent=None):
        super().__init__("Календарь Mail.ru", parent)
        self.setProperty("settingsSection", True)
        self.store = store
        self.selected_day = selected_day
        self.credentials = Credentials()
        self.worker = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(24)
        form.setVerticalSpacing(14)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.url = QLineEdit(store.get_setting("mail_url"))
        self.url.setPlaceholderText("https://calendar.mail.ru/principals/…/calendars/…/")
        form.addRow("Ссылка CalDAV", self.url)
        self.login = QLineEdit(store.get_setting("mail_login"))
        self.login.setPlaceholderText("Полный адрес почты")
        form.addRow("Логин", self.login)
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setPlaceholderText("Пароль внешнего приложения; пусто — использовать сохранённый")
        form.addRow("Пароль приложения", self.password)
        self.zone = QComboBox()
        self.zone.addItems(["Europe/Moscow", "UTC"])
        self.zone.setCurrentText(store.get_setting("mail_timezone", "Europe/Moscow"))
        form.addRow("Часовой пояс расписания", self.zone)
        self.remember = QCheckBox("Сохранить пароль в хранилище Windows")
        self.remember.setChecked(store.get_setting("mail_remember", "1") == "1" and self.credentials.can_remember)
        self.remember.setEnabled(self.credentials.can_remember)
        form.addRow("", self.remember)
        self.auto = QCheckBox("Обновлять при запуске приложения")
        self.auto.setChecked(store.get_setting("mail_auto", "1") == "1")
        form.addRow("", self.auto)
        layout.addLayout(form)
        layout.addSpacing(4)
        actions = QHBoxLayout()
        actions.setSpacing(12)
        self.save_button = QPushButton("Сохранить подключение и обновить")
        self.save_button.clicked.connect(self.save_connection)
        actions.addWidget(self.save_button)
        self.sync_button = QPushButton("Обновить из Mail.ru")
        self.sync_button.clicked.connect(self.sync)
        actions.addWidget(self.sync_button)
        actions.addStretch()
        layout.addLayout(actions)
        layout.addSpacing(4)
        self.status = QLabel("Последнее успешное обновление: " + (store.get_setting("mail_last_sync").replace("T", " ") or "ещё не было"))
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        note = QLabel("Загружаем 30 дней до и 90 дней после выбранной даты. Время отображается в выбранном часовом поясе. "
                      "Название и плановое время меняй в Mail.ru; категорию, факт и итоги — здесь. "
                      "Пропавшие записи сохраняются с отметкой «Проверить Mail.ru». Пароль не хранится в базе или GitHub.")
        note.setWordWrap(True)
        note.setObjectName("Muted")
        layout.addWidget(note)
        QTimer.singleShot(0, self.startup)

    @property
    def busy(self):
        return self.worker is not None

    def freeze_warning(self, day):
        if not self.store.get_setting('mail_url'):
            return ''
        config = CalendarConfig(self.store.get_setting('mail_url'), self.store.get_setting('mail_login'))
        return self.store.sync_warning(day, config.calendar_key)

    def sync_failed(self, text):
        if getattr(self, '_sync_context', None):
            config, start, end = self._sync_context
            try:
                self.store.record_sync_failure(config.calendar_key, start, end)
            except Exception:
                text += ' Не удалось сохранить результат попытки обновления.'
        self.show_status(text)

    def show_status(self, text):
        self.status.setText(text)
        self.message.emit(text)

    def startup(self):
        if self.store.get_setting("mail_url") and self.auto.isChecked():
            self.sync()

    def save_connection(self):
        if self.busy:
            return
        try:
            config = CalendarConfig(self.url.text().strip(), self.login.text().strip(), self.zone.currentText())
            config.validate()
            # Do not reinterpret already imported floating times by changing the display zone.
            old_zone = self.store.get_setting("mail_timezone", "Europe/Moscow")
            if config.timezone != old_zone and self.store.has_schedule_events():
                raise CalendarError("После появления событий часовой пояс менять нельзя: это изменит смысл сохранённого плана и факта.")
            old_url = self.store.get_setting("mail_url")
            old_login = self.store.get_setting("mail_login")
            if self.store.calendar_info() and (config.url != old_url or config.username.lower() != old_login.lower()):
                raise CalendarError("Замена календаря после импорта пока не поддерживается. Сначала сохрани резервную копию.")
            password = self.password.text() or self.credentials.get(config.calendar_key)
            if not password:
                raise CalendarError("Введи созданный пароль внешнего приложения.")
            self.credentials.set(config.calendar_key, password, self.remember.isChecked())
            for name, value in {
                "mail_url": config.url, "mail_login": config.username, "mail_timezone": config.timezone,
                "mail_remember": "1" if self.remember.isChecked() else "0",
                "mail_auto": "1" if self.auto.isChecked() else "0",
            }.items():
                self.store.set_setting(name, value)
            self.password.clear()
            self.sync()
        except CalendarError as exc:
            self.show_status(str(exc))
        except Exception:
            self.show_status("Не удалось сохранить подключение. Проверь настройки и повтори.")

    def sync(self):
        if self.busy:
            return
        self._sync_context = None
        try:
            config = CalendarConfig(self.store.get_setting("mail_url"), self.store.get_setting("mail_login"),
                                    self.store.get_setting("mail_timezone", "Europe/Moscow"))
            if not config.url:
                raise CalendarError("Сначала укажи подключение на вкладке «Настройки».")
            config.validate()
            self._sync_context = (config, *window_for_day(date.fromisoformat(self.selected_day())))
            password = self.credentials.get(config.calendar_key)
            if not password:
                raise CalendarError("Введи пароль приложения на вкладке «Настройки» и сохрани подключение.")
            self.worker = SyncThread(config, password, date.fromisoformat(self.selected_day()), self)
            self.worker.snapshot_ready.connect(self.apply_snapshot)
            self.worker.failed.connect(self.sync_failed)
            self.worker.finished.connect(self.finished)
            self.set_controls(False)
            self.show_status("Обновляем календарь Mail.ru…")
            self.worker.start()
            self.busy_changed.emit(True)
        except CalendarError as exc:
            self.sync_failed(str(exc))
        except Exception:
            if self.worker is not None and not self.worker.isRunning():
                self.worker.deleteLater()
                self.worker = None
                self.set_controls(True)
                self.busy_changed.emit(False)
            self.sync_failed("Не удалось начать обновление. Проверь настройки подключения.")

    def apply_snapshot(self, snapshot):
        try:
            result = self.store.apply_calendar_snapshot(snapshot)
            last = self.store.get_setting("mail_last_sync").replace("T", " ")
            if snapshot.complete:
                self.show_status(f"Mail.ru обновлён {last}: новых {result['added']}, изменено {result['updated']}, "
                                 f"требуют проверки {result['missing']}.")
            else:
                self.show_status(f"Mail.ru загружен частично: новых {result['added']}, изменено {result['updated']}; "
                                 f"недоступных записей {len(snapshot.unavailable)}. "
                                 "Прежние записи сохранены, исчезновения не проверялись. " + snapshot.unavailable[0])
            self.changed.emit()
        except Exception:
            self.sync_failed("Не удалось сохранить обновление. Предыдущие данные сохранены.")

    def set_controls(self, enabled):
        for control in (self.url, self.login, self.password, self.zone, self.auto, self.save_button, self.sync_button):
            control.setEnabled(enabled)
        self.remember.setEnabled(enabled and self.credentials.can_remember)

    def finished(self):
        self.set_controls(True)
        self.worker.deleteLater()
        self.worker = None
        self.busy_changed.emit(False)
