"""Qt Widgets account of Mail.ru events and app-only plans and facts."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from PySide6.QtCore import QDate, QDateTime, QTime, QTimer, Qt, QLocale, QSize
from PySide6.QtGui import QBrush, QIcon, QActionGroup, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDateEdit, QDateTimeEdit, QDialog,
    QDialogButtonBox, QFileDialog, QFormLayout, QFrame, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPushButton, QScrollArea, QSpinBox, QTableWidget, QTableWidgetItem,
    QTabWidget, QVBoxLayout, QWidget, QButtonGroup, QStackedWidget,
)

from .storage import Event, STATUSES, Store, default_data_dir
from .mail_ui import MailPanel


from .theme import apply_theme, current_theme, color as theme_color, icon
from .calendar_view import CalendarBoard, MONTHS, MONTHS_GEN, period_days, event_interval, color_for
from .inspector import EventInspector, plain_label
from .status_menu import EventStatusMenu
from .mini_calendar import MiniCalendar
from .date_picker import install_date_picker
from .input_wheel import install_input_wheel_guard
from .desktop import app_icon_path, create_desktop_shortcut as install_desktop_shortcut, shortcuts_available
from .local_event_dialog import LocalEventDialog
from .schedule import events_in_layer
from .instance import SingleInstance
from .backup_ui import BackupPanel
from .analytics import deviations
from .analytics_ui import AnalyticsPage
from .history_ui import HistoryPage


def qt_datetime(value: str) -> QDateTime:
    dt = datetime.fromisoformat(value)
    return QDateTime(QDate(dt.year, dt.month, dt.day), QTime(dt.hour, dt.minute, dt.second))


def as_iso(widget: QDateTimeEdit) -> str:
    return widget.dateTime().toString("yyyy-MM-ddTHH:mm:ss")


def short_time(value: str | None) -> str:
    if not value:
        return "—"
    return datetime.fromisoformat(value).strftime("%d.%m %H:%M")


def interval(start: str | None, end: str | None) -> str:
    return f"{short_time(start)} – {short_time(end)}" if start and end else "—"


def error_box(parent: QWidget, exc: Exception) -> None:
    from .diagnostics import record_error
    record_error('ui.action', exc)
    QMessageBox.warning(parent, "Не удалось выполнить действие", str(exc))


class EventDialog(QDialog):
    def __init__(self, store: Store, event: Event, parent: QWidget | None = None):
        super().__init__(parent)
        if event is None or event.source != "caldav":
            raise ValueError("Учёт доступен только для событий Mail.ru.")
        self.setWindowTitle("Учёт события Mail.ru")
        self.setMinimumWidth(600)
        self.resize(680, 720)
        if QApplication.primaryScreen():
            self.setMaximumHeight(max(550, QApplication.primaryScreen().availableGeometry().height() - 40))
        self._event = event
        self.store = store
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 22, 24, 22)
        outer.setSpacing(18)
        heading = plain_label("Карточка события", "EventTitle")
        outer.addWidget(heading)
        if event.source == 'caldav' and not (event.current_start or event.baseline_start or event.actual_start):
            # Withdrawn records retain their identity and history, but have no
            # editable interval. Opening them must not invent a current time.
            for value in (event.title, event.category + ' · Mail.ru',
                          'Событие убрано из актуального расписания: его нет в загруженном периоде Mail.ru. '
                          'Прежнее время и изменения сохранены в Истории.'):
                label = plain_label(value)
                label.setWordWrap(True)
                outer.addWidget(label)
            outer.addStretch()
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
            buttons.button(QDialogButtonBox.StandardButton.Close).setText('Закрыть')
            buttons.rejected.connect(self.reject)
            outer.addWidget(buttons)
            return
        content = QWidget()
        content.setObjectName("DialogContent")
        form = QFormLayout(content)
        form.setSpacing(13)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        scroll.setMinimumHeight(465)
        outer.addWidget(scroll)


        self.title_input = QLineEdit(event.title)
        form.addRow("Название", self.title_input)

        self.category_input = QComboBox()
        self.category_input.addItems([r["name"] for r in store.categories()])
        self.category_input.setCurrentText(event.category)
        form.addRow("Категория", self.category_input)

        def date_edit(value: str) -> QDateTimeEdit:
            control = QDateTimeEdit()
            control.setDisplayFormat("dd.MM.yyyy HH:mm")
            install_date_picker(control)
            control.setDateTime(qt_datetime(value))
            return control

        start, end = event.current_start, event.current_end
        self.start_input = date_edit(start)
        self.end_input = date_edit(end)
        form.addRow("Актуальный план: начало", self.start_input)
        form.addRow("Актуальный план: конец", self.end_input)
        for control in (self.title_input, self.start_input, self.end_input):
            control.setEnabled(False)
        info = QLabel("Название и актуальное время обновляются из Mail.ru. Категория, факт и комментарий сохраняются локально.")
        info.setWordWrap(True)
        form.addRow("", info)

        self.status_input = QComboBox()
        for key, label in STATUSES.items():
            self.status_input.addItem(label, key)
        self.status_input.setCurrentIndex(self.status_input.findData(event.status))
        form.addRow("Статус", self.status_input)

        self.fact_checkbox = QCheckBox("Указать фактическое время")
        self.fact_checkbox.setChecked(bool(event.actual_start))
        form.addRow("", self.fact_checkbox)
        self.fact_start = date_edit(event.actual_start or start)
        self.fact_end = date_edit(event.actual_end or end)
        self.fact_start.setEnabled(self.fact_checkbox.isChecked())
        self.fact_end.setEnabled(self.fact_checkbox.isChecked())
        self.fact_checkbox.toggled.connect(self.fact_start.setEnabled)
        self.fact_checkbox.toggled.connect(self.fact_end.setEnabled)
        form.addRow("Факт: начало", self.fact_start)
        form.addRow("Факт: конец", self.fact_end)

        self.note_input = QLineEdit(event.note)
        self.note_input.setPlaceholderText("Причина переноса, итог встречи и т. д.")
        form.addRow("Комментарий", self.note_input)
        if event.baseline_start:
            info = QLabel(f"🔒 Исходный план: {interval(event.baseline_start, event.baseline_end)} — не изменяется")
            info.setWordWrap(True)
            form.addRow("", info)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Сохранить")
        buttons.button(QDialogButtonBox.StandardButton.Save).setObjectName("Primary")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        outer.addWidget(buttons)

    def save(self) -> None:
        try:
            self.store.update_event(
                self._event.id, expected_revision=self._event.revision,
                category=self.category_input.currentText(), status=self.status_input.currentData(),
                actual_start=as_iso(self.fact_start) if self.fact_checkbox.isChecked() else None,
                actual_end=as_iso(self.fact_end) if self.fact_checkbox.isChecked() else None,
                note=self.note_input.text().strip(),
            )
            self.accept()
        except Exception as exc:
            error_box(self, exc)


class StatCard(QFrame):
    def __init__(self, name: str):
        super().__init__()
        self.setObjectName("Metric")
        v = QVBoxLayout(self)
        v.setContentsMargins(10, 6, 10, 6)
        v.setSpacing(1)
        title = QLabel(name)
        title.setObjectName("CardTitle")
        self.value = QLabel("—")
        self.value.setObjectName("CardValue")
        v.addWidget(title)
        v.addWidget(self.value)

    def set_value(self, text: str) -> None:
        self.value.setText(text)


class MainWindow(QMainWindow):
    def __init__(self, store: Store):
        super().__init__()
        self.store = store
        apply_theme(store.get_setting("ui_theme", "light"))
        self._selected_id = None
        self.mode = store.get_setting("ui_calendar_view", "week")
        if self.mode not in {"day", "week", "month", "agenda"}:
            self.mode = "week"
        self.setWindowTitle("Director Calendar — расписание руководителя")
        self.setMinimumSize(1000, 650)
        available = QApplication.primaryScreen().availableGeometry() if QApplication.primaryScreen() else None
        self.resize(max(1000, min(1480, available.width() - 40)) if available else 1480,
                    max(650, min(930, available.height() - 50)) if available else 930)
        root = QWidget()
        self.setCentralWidget(root)
        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        self.sidebar = QFrame()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(205)
        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(18, 25, 18, 20)
        side.setSpacing(10)
        brand = QHBoxLayout()
        logo = plain_label("D", "Logo")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setFixedSize(40, 40)
        brand.addWidget(logo)
        names = QVBoxLayout()
        names.setSpacing(2)
        names.addWidget(plain_label("DIRECTOR", "Brand"))
        names.addWidget(plain_label("CALENDAR", "BrandSub"))
        brand.addLayout(names)
        side.addLayout(brand)
        side.addSpacing(28)
        self.nav_group = QButtonGroup(self)
        self.nav_buttons = []
        for i, (label, name) in enumerate((("Календарь", "calendar"), ("Аналитика", "chart"),
                                          ("История", "history"), ("Настройки", "settings"))):
            button = QPushButton(label)
            button.setIcon(icon(name, theme_color("icon").name()))
            button.setIconSize(QSize(18, 18))
            button.setObjectName("Nav")
            button.setCheckable(True)
            button.clicked.connect(lambda checked, index=i: self.tabs.setCurrentIndex(index))
            self.nav_group.addButton(button, i)
            self.nav_buttons.append(button)
            side.addWidget(button)
        side.addSpacing(23)
        self.mini = MiniCalendar()
        self.mini.setFixedHeight(216)
        self.mini.clicked.connect(lambda day: self.date_input.setDate(day))
        self.mini.activated.connect(lambda day: self.date_input.setDate(day))
        side.addWidget(self.mini)
        side.addStretch()
        self.theme_toggle = self.button("", self.toggle_theme)
        self.theme_toggle.setObjectName("ThemeToggle")
        self.theme_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_toggle.setIconSize(QSize(18, 18))
        self._update_theme_controls()
        side.addWidget(self.theme_toggle)
        from . import __version__
        side.addWidget(plain_label("Версия " + __version__, "Muted"))
        shell.addWidget(self.sidebar)
        workspace = QWidget()
        workspace.setObjectName("Workspace")
        layout = QVBoxLayout(workspace)
        layout.setContentsMargins(24, 23, 24, 14)
        layout.setSpacing(18)
        head = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(4)
        self.page_title = plain_label("Календарь", "PageTitle")
        self.page_subtitle = plain_label("Рабочий ритм руководителя — в одном месте", "Muted")
        titles.addWidget(self.page_title)
        titles.addWidget(self.page_subtitle)
        head.addLayout(titles)
        head.addStretch()
        self.search = QLineEdit()
        self.search.setObjectName("Search")
        self.search.setPlaceholderText("Поиск в открытом периоде")
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(210)
        self.search.textChanged.connect(self.reload)
        head.addWidget(self.search)
        self.mail_refresh = self.button("Обновить Mail.ru", lambda: self.mail_panel.sync(), primary=True)
        self.mail_refresh.setIcon(icon("sync", "white"))
        head.addWidget(self.mail_refresh)
        layout.addLayout(head)
        self.mail_status = plain_label("", "Muted")
        self.mail_status.setWordWrap(True)
        self.mail_status.hide()
        layout.addWidget(self.mail_status)
        self.tabs = QTabWidget()
        self.tabs.tabBar().hide()
        layout.addWidget(self.tabs, 1)
        shell.addWidget(workspace, 1)
        self._build_day_tab()
        self._build_analytics_tab()
        self._build_history_tab()
        self._build_settings_tab()
        self.new_event_shortcut = QShortcut(QKeySequence.StandardKey.New, self)
        self.new_event_shortcut.activated.connect(self.add_event)
        self.tabs.currentChanged.connect(self.navigate)
        self.navigate(0)
        self.reload()

    def _update_theme_controls(self):
        dark = current_theme() == "dark"
        self.theme_toggle.setText("Светлая тема" if dark else "Тёмная тема")
        self.theme_toggle.setIcon(icon("sun" if dark else "moon"))
        self.theme_toggle.setToolTip("Переключить на светлую тему" if dark else "Переключить на тёмную тему")
        for button, name in zip(self.nav_buttons, ("calendar", "chart", "history", "settings")):
            button.setIcon(icon(name, theme_color("icon").name()))

    def toggle_theme(self):
        name = "light" if current_theme() == "dark" else "dark"
        self.store.set_setting("ui_theme", name)
        apply_theme(name)
        self._update_theme_controls()
        # Rebuild table foreground brushes; painted calendars use tokens directly.
        self.reload()

    def navigate(self, index):
        names = ("Календарь", "Аналитика", "История изменений", "Настройки")
        descriptions = ("Рабочий ритм руководителя — в одном месте", "План, факт и качество учёта за выбранный период",
                        "Изменения расписания и решений", "Подключение календаря и рабочие параметры")
        self.page_title.setText(names[index])
        self.page_subtitle.setText(descriptions[index])
        self.nav_buttons[index].setChecked(True)
        self.search.setVisible(index == 0)
        if index == 2:
            self.history_page.refresh()
        if index == 1 and self.analytics_page.dirty:
            self.analytics_page.refresh()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "inspector"):
            self.inspector.setVisible(self.width() >= 1320 and self.height() >= 820)
            self.calendar.set_compact(self.height() < 820)
        if hasattr(self, "search"):
            self.search.setFixedWidth(210 if self.width() >= 1240 else 150)
        if hasattr(self, "add_event_button"):
            self.add_event_button.setText("Добавить событие" if self.width() >= 1240 else "Добавить")
        if hasattr(self, "mini"):
            self.mini.setVisible(self.height() >= 800)

    def selected_day(self) -> str:
        return self.date_input.date().toString("yyyy-MM-dd")

    def selected_sync_day(self) -> str:
        return self.analytics_page.anchor.isoformat() if self.tabs.currentIndex() == 1 else self.selected_day()

    def calendar_date_changed(self, *_):
        if hasattr(self, 'analytics_page'):
            self.analytics_page.set_anchor(date.fromisoformat(self.selected_day()), refresh=False)
        self.reload()

    def button(self, title: str, callback, primary: bool = False) -> QPushButton:
        button = QPushButton(title)
        if primary:
            button.setObjectName("Primary")
        button.clicked.connect(callback)
        return button

    def _build_day_tab(self):
        page = QWidget()
        page.setObjectName("CalendarPage")
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(13)
        period = QHBoxLayout()
        self.period_title = plain_label("", "PeriodTitle")
        period.addWidget(self.period_title)
        period.addStretch()
        self.add_event_button = self.button("Добавить событие", self.add_event, primary=True)
        self.add_event_button.setIcon(icon("plus", "white"))
        self.add_event_button.setAccessibleName("Добавить событие")
        self.add_event_button.setToolTip("Добавить локальное событие · Ctrl+N")
        period.addWidget(self.add_event_button)
        segments = QFrame()
        segments.setObjectName("Segments")
        buttons = QHBoxLayout(segments)
        buttons.setContentsMargins(3, 3, 3, 3)
        buttons.setSpacing(1)
        self.view_group = QButtonGroup(self)
        self.view_buttons = {}
        for mode, label in (("day", "День"), ("week", "Неделя"), ("month", "Месяц"), ("agenda", "Список")):
            button = QPushButton(label)
            button.setObjectName("Segment")
            button.setCheckable(True)
            button.setChecked(mode == self.mode)
            button.clicked.connect(lambda checked, mode=mode: self.set_view(mode))
            self.view_group.addButton(button)
            self.view_buttons[mode] = button
            buttons.addWidget(button)
        period.addWidget(segments)
        v.addLayout(period)
        toolbar = QHBoxLayout()
        for label, offset in (("‹", -1), ("›", 1)):
            button = self.button(label, lambda checked=False, offset=offset: self.shift_period(offset))
            button.setObjectName("Arrow")
            toolbar.addWidget(button)
        toolbar.addWidget(self.button("Сегодня", lambda: self.set_date(self.calendar.today())))
        self.date_input = QDateEdit(QDate.currentDate())
        self.date_input.setLocale(QLocale(QLocale.Language.Russian))
        install_date_picker(self.date_input)
        self.date_input.setDisplayFormat("dd.MM.yyyy")
        self.date_input.setFixedWidth(126)
        self.date_input.dateChanged.connect(self.calendar_date_changed)
        toolbar.addWidget(self.date_input)
        self.layer = QComboBox()
        for label, key in (("Расписание", "current"), ("Исходный план", "baseline"), ("Факт", "actual")):
            self.layer.addItem(label, key)
        self.layer.currentIndexChanged.connect(self.reload)
        toolbar.addWidget(self.layer)
        toolbar.addStretch()
        self.freeze_button = self.button("Зафиксировать план", self.freeze)
        toolbar.addWidget(self.freeze_button)
        toolbar.addWidget(self.button("CSV", self.export))
        v.addLayout(toolbar)
        self.freeze_info = plain_label("", "Muted")
        self.freeze_info.setWordWrap(True)
        v.addWidget(self.freeze_info)
        body = QHBoxLayout()
        body.setSpacing(15)
        surface = QFrame()
        surface.setObjectName("Surface")
        content = QVBoxLayout(surface)
        content.setContentsMargins(1, 1, 1, 1)
        self.calendar_stack = QStackedWidget()
        self.calendar = CalendarBoard()
        self.calendar.selected.connect(self.select_event)
        self.calendar.activated.connect(self.open_event)
        self.calendar.context_requested.connect(self.show_event_context_menu)
        self.calendar.date_selected.connect(self.set_date)
        self.calendar.agenda_requested.connect(lambda: self.set_view("agenda"))
        self.calendar_stack.addWidget(self.calendar)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["Мероприятие", "Категория", "Исходный план", "Актуально", "Факт", "Статус", "Источник"])
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(54)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column, width in ((1, 100), (2, 155), (3, 155), (4, 155), (5, 140), (6, 120)):
            self.table.setColumnWidth(column, width)
        self.table.doubleClicked.connect(self.edit_event)
        self.table.itemSelectionChanged.connect(self.select_table_event)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_table_context_menu)
        self.calendar_stack.addWidget(self.table)
        content.addWidget(self.calendar_stack)
        body.addWidget(surface, 1)
        self.inspector = EventInspector()
        self.inspector.edit_requested.connect(self.edit_event)
        self.inspector.done_requested.connect(self.mark_done)
        body.addWidget(self.inspector)
        v.addLayout(body, 1)
        cards = QHBoxLayout()
        cards.setSpacing(6)
        self.cards = {name: StatCard(label) for name, label in (("planned", "В плане"), ("done", "Выполнено"),
            ("pending", "Без подтверждения"), ("unplanned", "Вне плана"), ("rate", "Исполнение"), ("gaps", "Окна 07–19"))}
        for card in self.cards.values():
            cards.addWidget(card, 1)
        v.addLayout(cards)
        self.tabs.addTab(page, "Календарь")

    def set_date(self, day):
        if isinstance(day, QDate):
            target = day
        else:
            target = QDate(day.year, day.month, day.day)
        if self.date_input.date() == target:
            return
        self.date_input.setDate(target)

    def set_view(self, mode):
        self.mode = mode
        self.view_buttons[mode].setChecked(True)
        self.store.set_setting("ui_calendar_view", mode)
        self.reload()

    def shift_period(self, offset):
        current = self.date_input.date()
        if self.mode == "month":
            current = current.addMonths(offset)
        else:
            current = current.addDays(offset * (7 if self.mode == "week" else 1))
        self.date_input.setDate(current)

    def add_event(self):
        day = date.fromisoformat(self.selected_sync_day())
        now = self.calendar.now().replace(tzinfo=None, second=0, microsecond=0)
        start = datetime.combine(day, now.time()) - timedelta(minutes=30)
        dialog = LocalEventDialog(self.store, start, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.event_id is not None:
            event = self.store.get_event(dialog.event_id)
            self._selected_id = event.id
            self.search.blockSignals(True)
            self.search.clear()
            self.search.blockSignals(False)
            self.layer.blockSignals(True)
            self.layer.setCurrentIndex(self.layer.findData("current"))
            self.layer.blockSignals(False)
            self.tabs.setCurrentIndex(0)
            target = datetime.fromisoformat(event.current_start or event.actual_start).date()
            self.set_date(target)
            self.reload()
            QTimer.singleShot(0, lambda: self._reveal_created_event(event.id))

    def _reveal_created_event(self, event_id):
        if self._selected_id != event_id:
            return
        if self.mode == "agenda" and event_id in self.row_ids:
            self.table.scrollToItem(self.table.item(self.row_ids.index(event_id), 0))
        elif self.mode in {"day", "week"}:
            self.calendar.reveal_event(event_id)

    def _find_event(self, event_id):
        try:
            return self.store.get_event(event_id)
        except KeyError:
            self._selected_id = None
            self.reload()
            return None

    def select_event(self, event_id):
        event = self._find_event(event_id)
        if event is None or event.source not in {"caldav", "local"}:
            return
        self._selected_id = event_id
        interval = event_interval(event, self.layer.currentData())
        day = self.calendar.clicked_day or (interval[0].date() if interval else date.fromisoformat(self.selected_day()))
        if day.isoformat() != self.selected_day() and day in period_days(date.fromisoformat(self.selected_day()), self.mode):
            self.set_date(day)
        else:
            self.reload()

    def select_table_event(self):
        row = self.table.currentRow()
        if 0 <= row < len(getattr(self, "row_ids", [])):
            self._selected_id = self.row_ids[row]
            selected = self._find_event(self._selected_id)
            if selected is not None:
                self.inspector.set_event(selected, self.store.calendar_info().get(self._selected_id))

    def open_event(self, event_id):
        event = self._find_event(event_id)
        if event is None or event.source not in {"caldav", "local"}:
            return
        self._selected_id = event_id
        self.edit_event()

    def mark_done(self):
        event_id = self.selected_event_id()
        if event_id is not None:
            self.set_event_status(event_id, "done")

    def set_event_status(self, event_id, status, expected_revision=None):
        try:
            self.store.update_event(event_id, expected_revision=expected_revision, status=status)
            self._selected_id = event_id
            self.reload()
        except Exception as exc:
            error_box(self, exc)

    def show_event_context_menu(self, event_id, global_pos):
        event = self._find_event(event_id)
        if event is None or event.source not in {"caldav", "local"}:
            return
        self.select_event(event_id)
        menu = EventStatusMenu(event, self)
        heading = menu.addAction("Статус события")
        heading.setEnabled(False)
        menu.addSeparator()
        group = QActionGroup(menu)
        group.setExclusive(True)
        for status, label in STATUSES.items():
            action = menu.addAction(label)
            action.setData(status)
            action.setCheckable(True)
            group.addAction(action)
            action.setChecked(status == event.status)
            action.triggered.connect(lambda checked, status=status: self.set_event_status(event_id, status, event.revision))
        try:
            menu.exec(global_pos)
        finally:
            menu.deleteLater()

    def show_table_context_menu(self, point):
        index = self.table.indexAt(point)
        if index.isValid() and 0 <= index.row() < len(self.row_ids):
            self.show_event_context_menu(self.row_ids[index.row()], self.table.viewport().mapToGlobal(point))

    def _build_analytics_tab(self):
        self.analytics_page = AnalyticsPage(self.store, date.fromisoformat(self.selected_day()))
        self.analytics_page.open_requested.connect(self.open_event)
        self.analytics_description = self.analytics_page.quality
        self.category_bars = self.analytics_page.category_bars
        self.analytics_table = self.analytics_page.category_table
        self.tabs.addTab(self.analytics_page, 'Аналитика')

    def _build_history_tab(self):
        self.history_page = HistoryPage(self.store)
        self.history_page.open_requested.connect(self.open_event)
        self.history_table = self.history_page.table
        self.tabs.addTab(self.history_page, 'История изменений')

    def _build_settings_tab(self):
        page = QWidget()
        page.setObjectName("FormContent")
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 8, 12, 24)
        v.setSpacing(20)
        self.mail_panel = MailPanel(self.store, self.selected_sync_day)
        self.mail_panel.changed.connect(self.reload)
        self.mail_panel.message.connect(self.mail_status.setText)
        self.mail_panel.message.connect(self.mail_status.show)
        self.mail_panel.busy_changed.connect(lambda busy: self.freeze_button.setEnabled(not busy))
        self.mail_panel.busy_changed.connect(lambda busy: self.mail_refresh.setEnabled(not busy))
        v.addWidget(self.mail_panel)
        options = QGroupBox("Контроль времени")
        options.setProperty("settingsSection", True)
        f = QFormLayout(options)
        f.setContentsMargins(24, 24, 24, 24)
        f.setHorizontalSpacing(24)
        f.setVerticalSpacing(16)
        f.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.tolerance = QSpinBox()
        self.tolerance.setMaximumWidth(160)
        self.tolerance.setRange(0, 180)
        self.tolerance.setSuffix(" мин")
        self.tolerance.setValue(int(self.store.get_setting("tolerance_minutes", "10")))
        f.addRow("Допустимое отклонение от плана", self.tolerance)
        save_options = self.button("Сохранить настройки", self.save_settings)
        save_options.setMaximumWidth(220)
        f.addRow("", save_options)
        rules_note = plain_label('Новые настройки применяются при следующей фиксации плана. Правила уже зафиксированных дней сохраняются.', 'Muted')
        rules_note.setWordWrap(True)
        f.addRow('', rules_note)
        v.addWidget(options)
        categories_box = QGroupBox("Категории и контроль выполнения")
        categories_box.setProperty("settingsSection", True)
        cv = QVBoxLayout(categories_box)
        cv.setContentsMargins(24, 24, 24, 24)
        cv.setSpacing(16)
        self.category_table = QTableWidget(0, 2)
        self.category_table.setMinimumHeight(240)
        self.category_table.setHorizontalHeaderLabels(["Категория", "Отслеживать выполнение"])
        self.category_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.category_table.verticalHeader().hide()
        self.category_table.verticalHeader().setDefaultSectionSize(38)
        self.category_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        cv.addWidget(self.category_table)
        add = QHBoxLayout()
        add.setSpacing(12)
        self.new_category = QLineEdit()
        self.new_category.setPlaceholderText("Название новой категории")
        add.addWidget(self.new_category)
        add.addWidget(self.button("Добавить категорию", self.add_category))
        cv.addLayout(add)
        v.addWidget(categories_box)
        launch_box = QGroupBox("Запуск приложения")
        launch_box.setProperty("settingsSection", True)
        launch_layout = QVBoxLayout(launch_box)
        launch_layout.setContentsMargins(24, 24, 24, 24)
        launch_layout.setSpacing(16)
        self.shortcut_button = self.button("Создать ярлык на рабочем столе", self.create_desktop_shortcut)
        self.shortcut_button.setEnabled(shortcuts_available())
        launch_layout.addWidget(self.shortcut_button, 0, Qt.AlignmentFlag.AlignLeft)
        launch_note = plain_label("Ярлык открывает календарь двойным щелчком, без окна командной строки.", "Muted")
        launch_note.setWordWrap(True)
        launch_layout.addWidget(launch_note)
        v.addWidget(launch_box)
        self.backup_panel = BackupPanel(self.store, lambda: not self.mail_panel.busy)
        self.backup_panel.notice.connect(self.mail_status.setText)
        self.backup_panel.notice.connect(self.mail_status.show)
        self.backup_panel.restored.connect(self._after_restore)
        v.addWidget(self.backup_panel)
        from .diagnostics_ui import DiagnosticsPanel
        self.diagnostics_panel = DiagnosticsPanel()
        v.addWidget(self.diagnostics_panel)
        v.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        self.tabs.addTab(scroll, "Настройки")

    def reload(self, *_):
        if not hasattr(self, "mail_panel"):
            return
        if getattr(self, '_restored', False) or (hasattr(self, 'backup_panel') and self.backup_panel.restoring):
            return
        day = self.selected_day()
        focus = date.fromisoformat(day)
        source_info = self.store.calendar_info()
        summary = self.store.day_summary(day)
        for key in ("planned", "done", "pending", "unplanned"):
            self.cards[key].set_value(str(summary[key]))
        self.cards["rate"].set_value("—" if summary["percent"] is None else f"{summary['percent']:.0f}%")
        self.cards["unplanned"].setToolTip(
            "Подтверждённо вне плана. Без фиксации плана: " + str(summary["unfixed"])
            + ". Переносы исходного плана остаются плановыми.")
        coverage = self.store.coverage_for_day(day)
        self.cards["gaps"].set_value(str(len(coverage["gaps"])))
        message = "Исходный план зафиксирован" if self.store.is_frozen(day) else "Исходный план на выбранный день ещё не зафиксирован"
        if coverage["gaps"]:
            message += "  ·  Окна: " + ", ".join(f"{start}–{end}" for start, end in coverage["gaps"])
        if coverage["overlaps"]:
            message += f"  ·  Пересечений: {coverage['overlaps']}"
        self.freeze_info.setText(message)
        days = period_days(focus, self.mode)
        if self.mode == "month":
            title = f"{MONTHS[focus.month - 1].capitalize()} {focus.year}"
        elif self.mode == "week":
            start, end = days[0], days[-1]
            title = (f"{start.day}–{end.day} {MONTHS_GEN[end.month - 1]} {end.year}" if start.month == end.month else
                     f"{start.day} {MONTHS_GEN[start.month - 1]} – {end.day} {MONTHS_GEN[end.month - 1]} {end.year}")
        else:
            title = f"{focus.day} {MONTHS_GEN[focus.month - 1]} {focus.year}"
        self.period_title.setText(title)
        self.mini.setSelectedDate(self.date_input.date())
        lower = days[0].isoformat() + "T00:00:00"
        upper = (days[-1] + timedelta(days=1)).isoformat() + "T00:00:00"
        query = self.search.text().strip().casefold()
        events = []
        for event in self.store.events_between(lower, upper):
            if query and query not in " ".join((event.title, event.category, event.note)).casefold():
                continue
            events.append(event)
        events = events_in_layer(events, self.layer.currentData(), datetime.fromisoformat(lower), datetime.fromisoformat(upper))
        visible_ids = {event.id for event in events}
        if self._selected_id not in visible_ids:
            self._selected_id = None
        self.calendar.set_data(focus, self.mode if self.mode != "agenda" else "day", self.layer.currentData(),
                               events, source_info, self._selected_id, self.store.get_setting("mail_timezone", "Europe/Moscow"))
        self.calendar_stack.setCurrentIndex(1 if self.mode == "agenda" else 0)
        selected = self.store.get_event(self._selected_id) if self._selected_id is not None else None
        self.inspector.set_event(selected, source_info.get(self._selected_id))
        day_start = datetime.combine(focus, time.min)
        day_end = day_start + timedelta(days=1)
        table_events = events_in_layer(events, self.layer.currentData(), day_start, day_end)
        self.table.blockSignals(True)
        self.table.setRowCount(len(table_events))
        self.row_ids = []
        tolerance = int(self.store.get_setting("tolerance_minutes", "10"))
        rules = self.store.baseline_rules()
        for row, ev in enumerate(table_events):
            self.row_ids.append(ev.id)
            event_tolerance = rules.get(ev.id, {}).get('tolerance_minutes', tolerance)
            start_delta, duration_delta = deviations(ev)
            deviates = bool(start_delta is not None and not source_info.get(ev.id, {}).get('baseline_all_day') and
                            (abs(start_delta) > event_tolerance or abs(duration_delta) > event_tolerance))
            status_label = STATUSES[ev.status] + (" · отклонение" if ev.status == "done" and deviates else "")
            remote = source_info.get(ev.id)
            if remote:
                if remote["missing"]:
                    status_label += " · проверить Mail.ru"
                elif remote["cancelled"] and ev.status != "cancelled":
                    status_label += " · отменено в Mail.ru"
            values = [ev.title, ev.category, interval(ev.baseline_start, ev.baseline_end),
                      interval(ev.current_start, ev.current_end), interval(ev.actual_start, ev.actual_end),
                      status_label, ev.source_label + (" · вне плана" if ev.is_postfactum else "")
                      + (" · весь день" if remote and remote["all_day"] else "")]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == 5:
                    item.setForeground(QBrush(theme_color("muted") if ev.status == "pending" else color_for(ev)[0]))
                item.setToolTip(ev.note or "Двойной щелчок — открыть карточку")
                self.table.setItem(row, col, item)
        if self._selected_id in self.row_ids:
            self.table.selectRow(self.row_ids.index(self._selected_id))
        else:
            self.table.clearSelection()
        self.table.blockSignals(False)
        self._reload_analytics(day, summary)
        self._reload_history()
        self._reload_categories()

    def _reload_analytics(self, day=None, summary=None):
        self.analytics_page.dirty = True
        if self.tabs.currentIndex() == 1:
            self.analytics_page.refresh()

    def _reload_history(self):
        self.history_page.dirty = True
        if self.tabs.currentIndex() == 2:
            self.history_page.refresh()

    def _reload_categories(self):
        cats = self.store.categories()
        self.category_table.setRowCount(len(cats))
        for row, cat in enumerate(cats):
            current = self.category_table.item(row, 0)
            existing = self.category_table.cellWidget(row, 1)
            if current and current.text() == cat["name"] and isinstance(existing, QCheckBox):
                existing.blockSignals(True)
                existing.setChecked(bool(cat["track"]))
                existing.setText("Да" if cat["track"] else "Нет")
                existing.blockSignals(False)
                continue
            self.category_table.setItem(row, 0, QTableWidgetItem(cat["name"]))
            cb = QCheckBox("Да" if cat["track"] else "Нет")
            cb.setContentsMargins(12, 0, 0, 0)
            cb.setChecked(bool(cat["track"]))
            cb.toggled.connect(lambda checked, name=cat["name"]: self.toggle_tracking(name, checked))
            self.category_table.setCellWidget(row, 1, cb)

    def selected_event_id(self) -> int | None:
        return self._selected_id

    def edit_event(self, *_):
        event_id = self.selected_event_id()
        if event_id is None:
            QMessageBox.information(self, "Выбери мероприятие", "Выбери событие в календаре или списке.")
            return
        event = self._find_event(event_id)
        if event is None:
            return
        dialog = (LocalEventDialog(self.store, datetime.fromisoformat(event.current_start or event.actual_start), event, self)
                  if event.source == "local" else EventDialog(self.store, event, self))
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if event.source == "local" and dialog.event_id is not None and self.tabs.currentIndex() == 0:
                updated = self._find_event(dialog.event_id)
                span = event_interval(updated, self.layer.currentData()) if updated else None
                days = period_days(date.fromisoformat(self.selected_day()), self.mode)
                if span and (span[1].date() < days[0] or span[0].date() > days[-1]):
                    self.set_date(span[0].date())
            self.reload()

    def freeze(self):
        if self.mail_panel.busy:
            QMessageBox.information(self, 'Обновление календаря', 'Дождись завершения обновления Mail.ru перед фиксацией плана.')
            return
        day = self.selected_day()
        coverage = self.store.coverage_for_day(day)
        warning = f"Зафиксировать исходное расписание на {day}? Отменить фиксацию нельзя."
        sync_warning = self.mail_panel.freeze_warning(day)
        if sync_warning:
            warning += '\n\n' + sync_warning + ' Рекомендуется сначала обновить календарь. Зафиксировать имеющиеся данные?'
        if coverage["gaps"]:
            warning += "\n\nВ расписании с 07:00 до 19:00 есть свободные окна: " + ", ".join(
                f"{start}–{end}" for start, end in coverage["gaps"])
        if coverage["overlaps"]:
            warning += f"\nОбнаружено пересечений: {coverage['overlaps']}"
        if QMessageBox.question(self, "Фиксация первоначального плана", warning,
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        if self.mail_panel.busy:
            QMessageBox.information(self, 'Обновление календаря', 'Началось обновление Mail.ru. Дождись его завершения и повтори фиксацию.')
            return
        try:
            count = self.store.freeze_day(day)
            self.reload()
            QMessageBox.information(self, "План сохранён", f"Зафиксировано мероприятий: {count}")
        except Exception as exc:
            error_box(self, exc)

    def export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Экспорт плана и факта", f"plan-fact-{self.selected_day()}.csv", "CSV (*.csv)")
        if path:
            try:
                self.store.export_csv(self.selected_day(), path)
                QMessageBox.information(self, "Готово", f"Отчёт сохранён:\n{path}")
            except Exception as exc:
                error_box(self, exc)

    def save_settings(self):
        self.store.set_setting("tolerance_minutes", str(self.tolerance.value()))
        self.reload()
        QMessageBox.information(self, "Готово", "Настройки сохранены")

    def add_category(self):
        try:
            self.store.add_category(self.new_category.text())
            self.new_category.clear()
            self.reload()
        except Exception as exc:
            error_box(self, exc)

    def toggle_tracking(self, category: str, checked: bool):
        self.store.set_category_tracking(category, checked)
        # Do not replace the active category checkbox while it is emitting its signal.
        day = self.selected_day()
        summary = self.store.day_summary(day)
        self.cards["planned"].set_value(str(summary["planned"]))
        self.cards["done"].set_value(str(summary["done"]))
        self.cards["pending"].set_value(str(summary["pending"]))
        self.cards["unplanned"].set_value(str(summary["unplanned"]))
        self.cards["rate"].set_value("—" if summary["percent"] is None else f"{summary['percent']:.0f}%")
        self._reload_analytics(day, summary)
        self._reload_history()
        self._reload_categories()

    def backup(self):
        self.backup_panel.make_manual()

    def _after_restore(self, _):
        self._restored = True
        self.mail_panel.auto.setChecked(False)
        self.close()

    def create_desktop_shortcut(self):
        try:
            install_desktop_shortcut()
            QMessageBox.information(self, "Ярлык создан", "На рабочем столе создан ярлык «Director Calendar».\n"
                                    "Открывай календарь двойным щелчком по нему.")
        except Exception as exc:
            error_box(self, exc)

    def closeEvent(self, event):
        if self.backup_panel.busy:
            QMessageBox.information(self, 'Резервные копии', 'Дождись завершения копирования или восстановления базы.')
            event.ignore()
            return
        if self.mail_panel.busy:
            QMessageBox.information(self, "Обновление календаря", "Дождись окончания обновления Mail.ru и закрой окно ещё раз.")
            event.ignore()
            return
        self.backup_panel.timer.stop()
        self.history_page.timer.stop()
        super().closeEvent(event)


def run_app() -> int:
    import sys
    QLocale.setDefault(QLocale(QLocale.Language.Russian))
    app = QApplication(sys.argv)
    from . import diagnostics
    from .diagnostics_ui import ErrorNotice
    error_notice = ErrorNotice(app)
    diagnostics.set_notifier(error_notice.raised.emit)
    instance = SingleInstance(default_data_dir() / 'director_control.db')
    if not instance.acquire():
        if not instance.notify():
            QMessageBox.information(None, 'Director Calendar', 'Приложение уже запущено или открывается. Дождись появления его окна.')
        return 0
    if app_icon_path().is_file():
        app.setWindowIcon(QIcon(str(app_icon_path())))
    install_input_wheel_guard(app)
    app.setStyle("Fusion")
    try:
        from .updates import prepare_version_update, record_version
        try:
            prepare_version_update(default_data_dir() / "director_control.db")
        except Exception as exc:
            diagnostics.record_error('database.startup', exc)
            from .recovery import offer_recovery
            offer_recovery(default_data_dir() / "director_control.db", exc)
            return 1
        store = Store()
        window = MainWindow(store)
        record_version(store)
        def activate():
            if window.isMinimized():
                window.showNormal()
            window.show()
            window.raise_()
            window.activateWindow()
        instance.activated.connect(activate)
        window.show()
        window.backup_panel.start()
        return app.exec()
    finally:
        diagnostics.set_notifier(None)
        instance.close()

