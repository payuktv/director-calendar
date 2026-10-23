"""Qt Widgets interface with optional read-only Mail.ru synchronization."""
from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta

from PySide6.QtCore import QDate, QDateTime, QTime, Qt, QLocale, QSize
from PySide6.QtGui import QColor, QBrush, QActionGroup
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDateEdit, QDateTimeEdit, QDialog,
    QDialogButtonBox, QFileDialog, QFormLayout, QFrame, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPushButton, QScrollArea, QSpinBox, QTableWidget, QTableWidgetItem,
    QTabWidget, QVBoxLayout, QWidget, QCalendarWidget, QButtonGroup, QStackedWidget,
)

from .storage import Event, STATUSES, Store, minutes_between
from .mail_ui import MailPanel


from .theme import STYLE, icon
from .calendar_view import CalendarBoard, MONTHS, MONTHS_GEN, period_days, event_interval, color_for
from .inspector import EventInspector, CategoryBars, plain_label
from .status_menu import EventStatusMenu


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
    QMessageBox.warning(parent, "Не удалось выполнить действие", str(exc))


class EventDialog(QDialog):
    def __init__(self, store: Store, day: str, parent: QWidget | None = None, event: Event | None = None, initial_start: datetime | None = None):
        super().__init__(parent)
        self.setWindowTitle("Редактирование мероприятия" if event else "Новое мероприятие")
        self.setMinimumWidth(600)
        self.resize(680, 720)
        if QApplication.primaryScreen():
            self.setMaximumHeight(max(550, QApplication.primaryScreen().availableGeometry().height() - 40))
        self.event = event
        self.store = store
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 22, 24, 22)
        outer.setSpacing(18)
        heading = plain_label("Карточка события" if event else "Новое событие", "EventTitle")
        outer.addWidget(heading)
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


        self.title_input = QLineEdit(event.title if event else "")
        self.title_input.setPlaceholderText("Например: совещание с руководителями")
        form.addRow("Название", self.title_input)

        self.category_input = QComboBox()
        self.category_input.addItems([r["name"] for r in store.categories()])
        if event:
            self.category_input.setCurrentText(event.category)
        form.addRow("Категория", self.category_input)

        def date_edit(value: str) -> QDateTimeEdit:
            control = QDateTimeEdit()
            control.setDisplayFormat("dd.MM.yyyy HH:mm")
            control.setCalendarPopup(True)
            control.setDateTime(qt_datetime(value))
            return control

        default_start = initial_start or datetime.fromisoformat(f"{day}T09:00:00")
        start = event.current_start if event else default_start.isoformat(timespec="seconds")
        end = event.current_end if event else (default_start + timedelta(hours=1)).isoformat(timespec="seconds")
        self.start_input = date_edit(start)
        self.end_input = date_edit(end)
        form.addRow("Актуальный план: начало", self.start_input)
        form.addRow("Актуальный план: конец", self.end_input)
        if event and event.source == "caldav":
            for control in (self.title_input, self.start_input, self.end_input):
                control.setEnabled(False)
            info = QLabel("Название и актуальное время обновляются из Mail.ru. Категория, факт и комментарий сохраняются локально.")
            info.setWordWrap(True)
            form.addRow("", info)

        self.status_input = QComboBox()
        for key, label in STATUSES.items():
            self.status_input.addItem(label, key)
        if event:
            self.status_input.setCurrentIndex(self.status_input.findData(event.status))
        form.addRow("Статус", self.status_input)

        self.fact_checkbox = QCheckBox("Указать фактическое время")
        self.fact_checkbox.setChecked(bool(event and event.actual_start))
        form.addRow("", self.fact_checkbox)
        self.fact_start = date_edit(event.actual_start if event and event.actual_start else start)
        self.fact_end = date_edit(event.actual_end if event and event.actual_end else end)
        self.fact_start.setEnabled(self.fact_checkbox.isChecked())
        self.fact_end.setEnabled(self.fact_checkbox.isChecked())
        self.fact_checkbox.toggled.connect(self.fact_start.setEnabled)
        self.fact_checkbox.toggled.connect(self.fact_end.setEnabled)
        form.addRow("Факт: начало", self.fact_start)
        form.addRow("Факт: конец", self.fact_end)

        self.note_input = QLineEdit(event.note if event else "")
        self.note_input.setPlaceholderText("Причина переноса, итог встречи и т. д.")
        form.addRow("Комментарий", self.note_input)
        if event and event.baseline_start:
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
            title = self.title_input.text().strip()
            category = self.category_input.currentText()
            start = as_iso(self.start_input)
            end = as_iso(self.end_input)
            if self.event:
                updates = dict(category=category, status=self.status_input.currentData(),
                               actual_start=as_iso(self.fact_start) if self.fact_checkbox.isChecked() else None,
                               actual_end=as_iso(self.fact_end) if self.fact_checkbox.isChecked() else None,
                               note=self.note_input.text().strip())
                if self.event.source != "caldav":
                    updates.update(title=title, current_start=start, current_end=end)
                self.store.update_event(self.event.id, **updates)
            else:
                eid = self.store.create_event(title, category, start, end)
                if self.status_input.currentData() != "pending" or self.fact_checkbox.isChecked() or self.note_input.text():
                    self.store.update_event(
                        eid, status=self.status_input.currentData(),
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
        v.setContentsMargins(14, 10, 14, 10)
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
            button.setIcon(icon(name, "#8B89A3"))
            button.setIconSize(QSize(18, 18))
            button.setObjectName("Nav")
            button.setCheckable(True)
            button.clicked.connect(lambda checked, index=i: self.tabs.setCurrentIndex(index))
            self.nav_group.addButton(button, i)
            self.nav_buttons.append(button)
            side.addWidget(button)
        side.addSpacing(23)
        self.mini = QCalendarWidget()
        self.mini.setLocale(QLocale(QLocale.Language.Russian))
        self.mini.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        self.mini.setHorizontalHeaderFormat(QCalendarWidget.HorizontalHeaderFormat.SingleLetterDayNames)
        self.mini.setFirstDayOfWeek(Qt.DayOfWeek.Monday)
        self.mini.setGridVisible(False)
        self.mini.setFixedHeight(204)
        self.mini.setMinimumWidth(165)
        self.mini.clicked.connect(lambda day: self.date_input.setDate(day))
        side.addWidget(self.mini)
        side.addSpacing(14)
        side.addWidget(plain_label("ИСТОЧНИКИ", "Eyebrow"))
        self.show_mail = QCheckBox("Mail.ru")
        self.show_manual = QCheckBox("Ручные записи")
        for control in (self.show_mail, self.show_manual):
            control.setChecked(True)
            control.toggled.connect(self.reload)
            side.addWidget(control)
        side.addStretch()
        side.addWidget(plain_label("ПЛАН / ФАКТ", "Eyebrow"))
        note = plain_label("Всё расписание. Один рабочий фокус.", "Muted")
        note.setWordWrap(True)
        side.addWidget(note)
        side.addSpacing(10)
        side.addWidget(plain_label("Версия 0.3.5", "Muted"))
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
        self.mail_refresh = self.button("Обновить", lambda: self.mail_panel.sync())
        self.mail_refresh.setIcon(icon("sync", "#85859D"))
        head.addWidget(self.mail_refresh)
        create = self.button("Событие", self.add_event, primary=True)
        create.setIcon(icon("plus", "white"))
        head.addWidget(create)
        layout.addLayout(head)
        self.tabs = QTabWidget()
        self.tabs.tabBar().hide()
        layout.addWidget(self.tabs, 1)
        self.mail_status = plain_label("Mail.ru: подключение в настройках", "Muted")
        self.mail_status.setWordWrap(True)
        layout.addWidget(self.mail_status)
        shell.addWidget(workspace, 1)
        self._build_day_tab()
        self._build_analytics_tab()
        self._build_history_tab()
        self._build_settings_tab()
        self.tabs.currentChanged.connect(self.navigate)
        self.navigate(0)
        self.reload()

    def navigate(self, index):
        names = ("Календарь", "Аналитика", "История изменений", "Настройки")
        descriptions = ("Рабочий ритм руководителя — в одном месте", "План и подтверждённый результат за выбранный день",
                        "Изменения расписания и решений", "Подключение календаря и рабочие параметры")
        self.page_title.setText(names[index])
        self.page_subtitle.setText(descriptions[index])
        self.nav_buttons[index].setChecked(True)
        self.search.setVisible(index == 0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "inspector"):
            self.inspector.setVisible(self.width() >= 1320 and self.height() >= 820)
            self.calendar.set_compact(self.height() < 820)
        if hasattr(self, "search"):
            self.search.setFixedWidth(210 if self.width() >= 1240 else 150)
        if hasattr(self, "mini"):
            self.mini.setVisible(self.height() >= 800)

    def selected_day(self) -> str:
        return self.date_input.date().toString("yyyy-MM-dd")

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
        self.date_input.setCalendarPopup(True)
        self.date_input.setDisplayFormat("dd.MM.yyyy")
        self.date_input.setFixedWidth(126)
        self.date_input.dateChanged.connect(self.reload)
        toolbar.addWidget(self.date_input)
        self.layer = QComboBox()
        for label, key in (("Актуальный план", "current"), ("Исходный план", "baseline"), ("Факт", "actual")):
            self.layer.addItem(label, key)
        self.layer.currentIndexChanged.connect(self.reload)
        toolbar.addWidget(self.layer)
        toolbar.addStretch()
        toolbar.addWidget(self.button("Зафиксировать план", self.freeze))
        toolbar.addWidget(self.button("CSV", self.export))
        v.addLayout(toolbar)
        cards = QHBoxLayout()
        cards.setSpacing(8)
        self.cards = {name: StatCard(label) for name, label in (("planned", "В плане"), ("done", "Выполнено"),
            ("pending", "Без подтверждения"), ("unplanned", "Вне плана"), ("rate", "Исполнение"), ("gaps", "Окна 07–19"))}
        for card in self.cards.values():
            cards.addWidget(card, 1)
        v.addLayout(cards)
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
        self.calendar.slot_requested.connect(self.add_at_time)
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
        self.inspector.delete_requested.connect(self.delete_event)
        self.inspector.done_requested.connect(self.mark_done)
        body.addWidget(self.inspector)
        v.addLayout(body, 1)
        footer = QHBoxLayout()
        footer.addWidget(plain_label("Правый клик — статус · Двойной — открыть или создать", "Muted"))
        footer.addStretch()
        self.open_selected_button = self.button("Открыть карточку", self.edit_event)
        self.delete_selected_button = self.button("Удалить", self.delete_event)
        self.delete_selected_button.setObjectName("Danger")
        footer.addWidget(self.open_selected_button)
        footer.addWidget(self.delete_selected_button)
        v.addLayout(footer)
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

    def select_event(self, event_id):
        self._selected_id = event_id
        event = self.store.get_event(event_id)
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
            selected = self.store.get_event(self._selected_id)
            self.inspector.set_event(selected, self.store.calendar_info().get(self._selected_id))
            self.open_selected_button.setEnabled(True)
            self.delete_selected_button.setEnabled(selected.source != "caldav" and not selected.baseline_start)

    def open_event(self, event_id):
        self._selected_id = event_id
        self.edit_event()

    def add_at_time(self, day, minute):
        self.set_date(day)
        start = datetime.combine(day, time.min) + timedelta(minutes=minute)
        dialog = EventDialog(self.store, day.isoformat(), self, initial_start=start)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.reload()

    def mark_done(self):
        event_id = self.selected_event_id()
        if event_id is not None:
            self.set_event_status(event_id, "done")

    def set_event_status(self, event_id, status):
        try:
            self.store.update_event(event_id, status=status)
            self._selected_id = event_id
            self.reload()
        except Exception as exc:
            error_box(self, exc)

    def show_event_context_menu(self, event_id, global_pos):
        self.select_event(event_id)
        event = self.store.get_event(event_id)
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
            action.triggered.connect(lambda checked, status=status: self.set_event_status(event_id, status))
        try:
            menu.exec(global_pos)
        finally:
            menu.deleteLater()

    def show_table_context_menu(self, point):
        index = self.table.indexAt(point)
        if index.isValid() and 0 <= index.row() < len(self.row_ids):
            self.show_event_context_menu(self.row_ids[index.row()], self.table.viewport().mapToGlobal(point))

    def _build_analytics_tab(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 18, 0, 0)
        caption = QLabel("Аналитика за выбранную дату")
        caption.setStyleSheet("font-size: 18px; font-weight: 700")
        v.addWidget(caption)
        self.analytics_description = QLabel("")
        self.analytics_description.setWordWrap(True)
        v.addWidget(self.analytics_description)
        legend = QHBoxLayout()
        for label, color in (("Исходный план", "#A28DE8"), ("Подтверждённый факт", "#43A88D")):
            item = plain_label("●  " + label)
            item.setStyleSheet(f"color: {color};")
            legend.addWidget(item)
        legend.addStretch()
        v.addLayout(legend)
        self.category_bars = CategoryBars()
        chart_scroll = QScrollArea()
        chart_scroll.setWidgetResizable(True)
        chart_scroll.setWidget(self.category_bars)
        chart_scroll.setMinimumHeight(230)
        v.addWidget(chart_scroll, 1)
        self.analytics_table = QTableWidget(0, 3)
        self.analytics_table.setHorizontalHeaderLabels(["Категория", "Первоначально, мин", "Фактически подтверждено, мин"])
        self.analytics_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.analytics_table.verticalHeader().hide()
        self.analytics_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        v.addWidget(self.analytics_table, stretch=1)
        note = QLabel("Факт времени учитывается только если в карточке заполнены начало и конец. Статус «Выполнено» без времени не создаёт вымышленных часов.")
        note.setObjectName("Muted")
        note.setWordWrap(True)
        v.addWidget(note)
        self.tabs.addTab(page, "Аналитика")

    def _build_history_tab(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 18, 0, 0)
        v.addWidget(QLabel("Последние 300 изменений · журнал хранится локально"))
        self.history_table = QTableWidget(0, 4)
        self.history_table.setHorizontalHeaderLabels(["Когда", "Мероприятие", "Действие", "Детали"])
        self.history_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.history_table.setColumnWidth(0, 165)
        self.history_table.setColumnWidth(1, 250)
        self.history_table.setColumnWidth(2, 130)
        self.history_table.verticalHeader().hide()
        self.history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        v.addWidget(self.history_table)
        self.tabs.addTab(page, "История изменений")

    def _build_settings_tab(self):
        page = QWidget()
        page.setObjectName("FormContent")
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 18, 0, 0)
        self.mail_panel = MailPanel(self.store, self.selected_day)
        self.mail_panel.changed.connect(self.reload)
        self.mail_panel.message.connect(self.mail_status.setText)
        v.addWidget(self.mail_panel)
        options = QGroupBox("Контроль времени")
        f = QFormLayout(options)
        self.tolerance = QSpinBox()
        self.tolerance.setRange(0, 180)
        self.tolerance.setSuffix(" мин")
        self.tolerance.setValue(int(self.store.get_setting("tolerance_minutes", "10")))
        f.addRow("Допустимое отклонение от плана", self.tolerance)
        f.addRow("", self.button("Сохранить настройки", self.save_settings))
        v.addWidget(options)
        categories_box = QGroupBox("Категории и контроль выполнения")
        cv = QVBoxLayout(categories_box)
        self.category_table = QTableWidget(0, 2)
        self.category_table.setHorizontalHeaderLabels(["Категория", "Отслеживать выполнение"])
        self.category_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.category_table.verticalHeader().hide()
        self.category_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        cv.addWidget(self.category_table)
        add = QHBoxLayout()
        self.new_category = QLineEdit()
        self.new_category.setPlaceholderText("Название новой категории")
        add.addWidget(self.new_category)
        add.addWidget(self.button("Добавить категорию", self.add_category))
        cv.addLayout(add)
        v.addWidget(categories_box)
        data_box = QGroupBox("Данные и безопасность")
        d = QVBoxLayout(data_box)
        path_label = QLabel(f"База данных: {self.store.path}")
        path_label.setWordWrap(True)
        d.addWidget(path_label)
        d.addWidget(self.button("Создать резервную копию", self.backup))
        d.addWidget(QLabel("Рабочая база остаётся на этом компьютере. Подключение к Mail.ru используется только для чтения."))
        v.addWidget(data_box)
        v.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        self.tabs.addTab(scroll, "Настройки")

    def reload(self, *_):
        if not hasattr(self, "mail_panel"):
            return
        day = self.selected_day()
        focus = date.fromisoformat(day)
        source_info = self.store.calendar_info()
        summary = self.store.day_summary(day)
        for key in ("planned", "done", "pending", "unplanned"):
            self.cards[key].set_value(str(summary[key]))
        self.cards["rate"].set_value("—" if summary["percent"] is None else f"{summary['percent']:.0f}%")
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
            if event.source == "caldav" and not self.show_mail.isChecked():
                continue
            if event.source != "caldav" and not self.show_manual.isChecked():
                continue
            if query and query not in " ".join((event.title, event.category, event.note)).casefold():
                continue
            events.append(event)
        visible_ids = {event.id for event in events}
        if self._selected_id not in visible_ids:
            self._selected_id = None
        self.calendar.set_data(focus, self.mode if self.mode != "agenda" else "day", self.layer.currentData(),
                               events, source_info, self._selected_id, self.store.get_setting("mail_timezone", "Europe/Moscow"))
        self.calendar_stack.setCurrentIndex(1 if self.mode == "agenda" else 0)
        selected = self.store.get_event(self._selected_id) if self._selected_id is not None else None
        self.inspector.set_event(selected, source_info.get(self._selected_id))
        self.open_selected_button.setEnabled(selected is not None)
        self.delete_selected_button.setEnabled(selected is not None and selected.source != "caldav" and not selected.baseline_start)
        day_start = datetime.combine(focus, time.min)
        day_end = day_start + timedelta(days=1)
        table_events = [event for event in events if any(
            span and span[0] < day_end and span[1] > day_start
            for span in (event_interval(event, key) for key in ("current", "baseline", "actual")))]
        self.table.blockSignals(True)
        self.table.setRowCount(len(table_events))
        self.row_ids = []
        tolerance = int(self.store.get_setting("tolerance_minutes", "10"))
        for row, ev in enumerate(table_events):
            self.row_ids.append(ev.id)
            deviates = bool(ev.actual_start and ev.baseline_start and
                            (abs(minutes_between(ev.baseline_start, ev.actual_start)) > tolerance or
                             abs(minutes_between(ev.baseline_end, ev.actual_end)) > tolerance))
            status_label = STATUSES[ev.status] + (" · отклонение" if ev.status == "done" and deviates else "")
            remote = source_info.get(ev.id)
            if remote:
                if remote["missing"]:
                    status_label += " · проверить Mail.ru"
                elif remote["cancelled"] and ev.status != "cancelled":
                    status_label += " · отменено в Mail.ru"
            values = [ev.title, ev.category, interval(ev.baseline_start, ev.baseline_end),
                      interval(ev.current_start, ev.current_end), interval(ev.actual_start, ev.actual_end),
                      status_label, ("Mail.ru" if ev.source == "caldav" else "Вручную") + (" · весь день" if remote and remote["all_day"] else "")]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == 5:
                    item.setForeground(QBrush(QColor("#85889B") if ev.status == "pending" else color_for(ev)[0]))
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

    def _reload_analytics(self, day: str, summary: dict):
        self.analytics_description.setText(
            f"Исходный план: {summary['planned']} контролируемых мероприятий · "
            f"выполнено: {summary['done']} · частично: {summary['partial']} · "
            f"отменено: {summary['cancelled']} · перенесено: {summary['moved']} · "
            f"не подтверждено: {summary['pending']} · вне плана: {summary['unplanned']}."
        )
        totals = self.store.category_totals(day)
        self.category_bars.set_values(totals)
        self.analytics_table.setRowCount(len(totals))
        for row, (cat, planned, actual) in enumerate(totals):
            for col, val in enumerate((cat, str(planned), str(actual))):
                self.analytics_table.setItem(row, col, QTableWidgetItem(val))

    def _reload_history(self):
        logs = self.store.audit_log()
        self.history_table.setRowCount(len(logs))
        for row, log in enumerate(logs):
            details = log["details"]
            try:
                details = json.dumps(json.loads(details), ensure_ascii=False, separators=(", ", ": "))
            except ValueError:
                pass
            for col, val in enumerate((log["changed_at"].replace("T", " "), log["title"], log["action"], details)):
                item = QTableWidgetItem(str(val))
                item.setToolTip(str(val))
                self.history_table.setItem(row, col, item)

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

    def add_event(self):
        dialog = EventDialog(self.store, self.selected_day(), self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.reload()

    def edit_event(self, *_):
        event_id = self.selected_event_id()
        if event_id is None:
            QMessageBox.information(self, "Выбери мероприятие", "Выбери событие в календаре или списке.")
            return
        dialog = EventDialog(self.store, self.selected_day(), self, self.store.get_event(event_id))
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.reload()

    def delete_event(self):
        event_id = self.selected_event_id()
        if event_id is None:
            return
        if QMessageBox.question(self, "Удаление", "Удалить выбранное мероприятие? Действие попадёт в журнал.") != QMessageBox.StandardButton.Yes:
            return
        try:
            self.store.delete_event(event_id)
            self._selected_id = None
            self.reload()
        except Exception as exc:
            error_box(self, exc)

    def freeze(self):
        day = self.selected_day()
        coverage = self.store.coverage_for_day(day)
        warning = f"Зафиксировать исходное расписание на {day}? Отменить фиксацию нельзя."
        if coverage["gaps"]:
            warning += "\n\nВ расписании с 07:00 до 19:00 есть свободные окна: " + ", ".join(
                f"{start}–{end}" for start, end in coverage["gaps"])
        if coverage["overlaps"]:
            warning += f"\nОбнаружено пересечений: {coverage['overlaps']}"
        if QMessageBox.question(self, "Фиксация первоначального плана", warning) != QMessageBox.StandardButton.Yes:
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
        self._reload_categories()

    def backup(self):
        try:
            saved = self.store.backup()
            QMessageBox.information(self, "Резервная копия создана", str(saved))
        except Exception as exc:
            error_box(self, exc)

    def closeEvent(self, event):
        if self.mail_panel.busy:
            QMessageBox.information(self, "Обновление календаря", "Дождись окончания обновления Mail.ru и закрой окно ещё раз.")
            event.ignore()
            return
        super().closeEvent(event)


def run_app() -> int:
    import sys
    QLocale.setDefault(QLocale(QLocale.Language.Russian))
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = MainWindow(Store())
    window.show()
    return app.exec()
