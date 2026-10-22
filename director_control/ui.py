"""Qt Widgets interface with optional read-only Mail.ru synchronization."""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import QDate, QDateTime, QTime, Qt
from PySide6.QtGui import QColor, QBrush, QFont
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDateEdit, QDateTimeEdit, QDialog,
    QDialogButtonBox, QFileDialog, QFormLayout, QFrame, QGridLayout, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPushButton, QScrollArea, QSpinBox, QSplitter, QTableWidget, QTableWidgetItem,
    QTabWidget, QVBoxLayout, QWidget, QProgressBar,
)

from .storage import Event, STATUSES, Store, minutes_between
from .mail_ui import MailPanel


STYLE = """
QMainWindow, QWidget { background-color: #F5F7FB; color: #172238; font-family: 'Segoe UI', Arial; font-size: 12px; }
QTabWidget::pane { border: 0; }
QTabBar::tab { background: #E9EDF5; color: #526079; padding: 11px 22px; margin-right: 5px;
               border-top-left-radius: 8px; border-top-right-radius: 8px; }
QTabBar::tab:selected { background: #FFFFFF; color: #305DBB; font-weight: 700; }
QLabel#AppTitle { font-size: 25px; font-weight: 750; color: #182840; }
QLabel#Muted { color: #79869A; }
QLabel#CardTitle { font-size: 12px; color: #71809A; }
QLabel#CardValue { font-size: 23px; color: #243858; font-weight: 750; }
QFrame#Card, QGroupBox { background: white; border: 1px solid #E5EAF2; border-radius: 12px; }
QGroupBox { font-weight: 700; margin-top: 12px; padding: 16px; }
QGroupBox::title { subcontrol-origin: margin; left: 18px; padding: 0 6px; }
QPushButton { background: white; border: 1px solid #D9E2EF; border-radius: 8px;
              padding: 9px 13px; font-weight: 600; }
QPushButton:hover { background: #EAF1FE; }
QPushButton#Primary { color: white; background: #3567CB; border-color: #3567CB; }
QPushButton#Primary:hover { background: #2855B1; }
QPushButton#Danger { color: #B23B51; }
QTableWidget { background: white; alternate-background-color: #F9FAFD; border: 1px solid #E4EAF1;
               border-radius: 10px; selection-background-color: #DFEAFD;
               selection-color: #243858; gridline-color: #F1F4F9; }
QHeaderView::section { background: #F0F4FA; border: 0; border-right: 1px solid #E5EAF2;
                       padding: 10px; font-weight: 700; color: #586982; }
QLineEdit, QComboBox, QDateTimeEdit, QDateEdit, QSpinBox { background: white;
        border: 1px solid #D9E2EF; border-radius: 7px; padding: 6px; min-height: 22px; }
QProgressBar { background: #EDF2FA; border: none; border-radius: 6px; height: 14px; }
QProgressBar::chunk { background: #4076D3; border-radius: 6px; }
"""


def qt_datetime(value: str) -> QDateTime:
    dt = datetime.fromisoformat(value)
    return QDateTime(QDate(dt.year, dt.month, dt.day), QTime(dt.hour, dt.minute))


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
    def __init__(self, store: Store, day: str, parent: QWidget | None = None, event: Event | None = None):
        super().__init__(parent)
        self.setWindowTitle("Редактирование мероприятия" if event else "Новое мероприятие")
        self.setMinimumWidth(540)
        self.event = event
        self.store = store
        form = QFormLayout(self)
        form.setSpacing(12)

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

        start = event.current_start if event else f"{day}T09:00:00"
        end = event.current_end if event else f"{day}T10:00:00"
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
        form.addRow(buttons)

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
        self.setObjectName("Card")
        v = QVBoxLayout(self)
        v.setContentsMargins(18, 14, 18, 14)
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
        self.setWindowTitle("Director Control — План / Факт")
        self.resize(1400, 820)
        self.setMinimumSize(1080, 620)
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(26, 19, 26, 18)
        layout.setSpacing(16)
        head = QHBoxLayout()
        titlebox = QVBoxLayout()
        title = QLabel("DIRECTOR CONTROL")
        title.setObjectName("AppTitle")
        subtitle = QLabel("Контроль расписания руководителя  ·  План / Факт")
        subtitle.setObjectName("Muted")
        titlebox.addWidget(title)
        titlebox.addWidget(subtitle)
        head.addLayout(titlebox)
        head.addStretch()
        badge = QLabel("●  Версия 0.2.3  ·  Mail.ru — только чтение")
        badge.setStyleSheet("color: #4278A7; background: #E6F1FC; padding: 10px; border-radius: 7px;")
        head.addWidget(badge)
        layout.addLayout(head)
        self.mail_status = QLabel("Mail.ru: подключение на вкладке «Настройки»")
        self.mail_status.setObjectName("Muted")
        self.mail_status.setWordWrap(True)
        layout.addWidget(self.mail_status)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        self._build_day_tab()
        self._build_analytics_tab()
        self._build_history_tab()
        self._build_settings_tab()
        self.reload()

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
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 16, 0, 0)
        toolbar = QHBoxLayout()
        self.date_input = QDateEdit(QDate.currentDate())
        self.date_input.setCalendarPopup(True)
        self.date_input.setDisplayFormat("dd.MM.yyyy")
        self.date_input.dateChanged.connect(self.reload)
        toolbar.addWidget(QLabel("Дата:"))
        toolbar.addWidget(self.date_input)
        toolbar.addWidget(self.button("←", lambda: self.date_input.setDate(self.date_input.date().addDays(-1))))
        toolbar.addWidget(self.button("→", lambda: self.date_input.setDate(self.date_input.date().addDays(1))))
        toolbar.addStretch()
        self.mail_refresh = self.button("Обновить Mail.ru", lambda: self.mail_panel.sync())
        toolbar.addWidget(self.mail_refresh)
        toolbar.addWidget(self.button("Зафиксировать план", self.freeze))
        toolbar.addWidget(self.button("Экспорт CSV", self.export))
        toolbar.addWidget(self.button("+ Мероприятие", self.add_event, primary=True))
        v.addLayout(toolbar)

        cards = QHBoxLayout()
        self.cards = {name: StatCard(label) for name, label in [
            ("planned", "В исходном плане"),
            ("done", "Выполнено"),
            ("pending", "Не подтверждено"),
            ("unplanned", "Вне плана"),
            ("rate", "Исполнение"),
            ("gaps", "Окна 07–19"),
        ]}
        for card in self.cards.values():
            cards.addWidget(card)
        v.addLayout(cards)
        self.freeze_info = QLabel("")
        self.freeze_info.setObjectName("Muted")
        v.addWidget(self.freeze_info)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["Мероприятие", "Категория", "Исходный план", "Актуальный план", "Факт", "Статус", "Тип"])
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.setSortingEnabled(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c, width in [(1, 130), (2, 180), (3, 180), (4, 180), (5, 160), (6, 120)]:
            self.table.setColumnWidth(c, width)
        self.table.doubleClicked.connect(self.edit_event)
        v.addWidget(self.table, stretch=1)

        bottom = QHBoxLayout()
        help_label = QLabel("Двойной щелчок по строке — изменить факт, статус или актуальное время")
        help_label.setObjectName("Muted")
        bottom.addWidget(help_label)
        bottom.addStretch()
        bottom.addWidget(self.button("Изменить", self.edit_event))
        remove_btn = self.button("Удалить", self.delete_event)
        remove_btn.setObjectName("Danger")
        bottom.addWidget(remove_btn)
        v.addLayout(bottom)
        self.tabs.addTab(page, "План / Факт")

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
        day = self.selected_day()
        events = self.store.daily_events(day)
        source_info = self.store.calendar_info()
        summary = self.store.day_summary(day)
        self.cards["planned"].set_value(str(summary["planned"]))
        self.cards["done"].set_value(str(summary["done"]))
        self.cards["pending"].set_value(str(summary["pending"]))
        self.cards["unplanned"].set_value(str(summary["unplanned"]))
        self.cards["rate"].set_value("—" if summary["percent"] is None else f"{summary['percent']:.0f}%")
        coverage = self.store.coverage_for_day(day)
        self.cards["gaps"].set_value(str(len(coverage["gaps"])))
        message = "🔒 Первоначальный план зафиксирован" if self.store.is_frozen(day) else \
                  "○ Первоначальный план ещё не зафиксирован — новые мероприятия не считаются планом до фиксации"
        if coverage["gaps"]:
            message += "   |   Свободные окна: " + ", ".join(f"{start}–{end}" for start, end in coverage["gaps"])
        if coverage["overlaps"]:
            message += f"   |   Пересечения: {coverage['overlaps']}"
        self.freeze_info.setText(message)
        self.table.setRowCount(len(events))
        self.row_ids = []
        tolerance = int(self.store.get_setting("tolerance_minutes", "10"))
        for row, ev in enumerate(events):
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
                      status_label, ("Вне плана" if not ev.baseline_start else "Из плана") +
                      (" · Mail.ru" if remote else "") + (" · весь день" if remote and remote["all_day"] else "")]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == 5:
                    item.setForeground(QBrush(QColor({"done": "#168C6F", "partial": "#B77B16", "cancelled": "#BE4358",
                                                     "moved": "#486CB5", "pending": "#7B879B"}[ev.status])))
                item.setToolTip(ev.note or "Двойной щелчок — редактировать")
                self.table.setItem(row, col, item)
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
            self.category_table.setItem(row, 0, QTableWidgetItem(cat["name"]))
            cb = QCheckBox("Да" if cat["track"] else "Нет")
            cb.setChecked(bool(cat["track"]))
            cb.toggled.connect(lambda checked, name=cat["name"]: self.toggle_tracking(name, checked))
            self.category_table.setCellWidget(row, 1, cb)

    def selected_event_id(self) -> int | None:
        row = self.table.currentRow()
        return self.row_ids[row] if 0 <= row < len(self.row_ids) else None

    def add_event(self):
        dialog = EventDialog(self.store, self.selected_day(), self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.reload()

    def edit_event(self, *_):
        event_id = self.selected_event_id()
        if event_id is None:
            QMessageBox.information(self, "Выбери мероприятие", "Сначала выбери строку в таблице.")
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
        # Reload only cards and analytics, not categories, to avoid replacing a checkbox during its signal.
        day = self.selected_day()
        summary = self.store.day_summary(day)
        self.cards["planned"].set_value(str(summary["planned"]))
        self.cards["done"].set_value(str(summary["done"]))
        self.cards["pending"].set_value(str(summary["pending"]))
        self.cards["unplanned"].set_value(str(summary["unplanned"]))
        self.cards["rate"].set_value("—" if summary["percent"] is None else f"{summary['percent']:.0f}%")
        self._reload_analytics(day, summary)

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
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = MainWindow(Store())
    window.show()
    return app.exec()
