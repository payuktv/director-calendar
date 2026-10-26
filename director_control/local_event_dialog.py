"""Create and edit app-only plans or unplanned events recorded after the fact."""
from datetime import datetime, timedelta

from PySide6.QtCore import QDate, QDateTime, QTime, Qt
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDateTimeEdit, QDialog, QDialogButtonBox,
    QFormLayout, QHBoxLayout, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from .date_picker import install_date_picker
from .inspector import plain_label
from .storage import STATUSES


class LocalEventDialog(QDialog):
    def __init__(self, store, start: datetime, event=None, parent=None):
        super().__init__(parent)
        if event is not None and event.source != "local":
            raise ValueError("Эта форма предназначена для локальных событий.")
        self.store, self._event = store, event
        self.event_id = event.id if event else None
        self._saved = False
        self.setWindowTitle("Локальное событие" if event else "Добавить событие")
        self.setMinimumWidth(600)
        self.resize(680, 720)
        if QApplication.primaryScreen():
            self.setMaximumHeight(max(550, QApplication.primaryScreen().availableGeometry().height() - 40))
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 22, 24, 22)
        outer.setSpacing(14)
        outer.addWidget(plain_label("Локальное событие" if event else "Добавить событие", "EventTitle"))
        note = plain_label("Сохраняется в приложении и не отправляется в Mail.ru.", "Muted")
        note.setWordWrap(True)
        outer.addWidget(note)
        content = QWidget()
        content.setObjectName("DialogContent")
        self.form = QFormLayout(content)
        self.form.setContentsMargins(0, 6, 4, 6)
        self.form.setHorizontalSpacing(18)
        self.form.setVerticalSpacing(14)
        self.form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        self.form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
        self.title_input = QLineEdit(event.title if event else "")
        self.title_input.setMaxLength(200)
        self.title_input.setPlaceholderText("Что произошло или что нужно запланировать")
        self.form.addRow("Название", self.title_input)
        self.category_input = QComboBox()
        self.category_input.addItems(row["name"] for row in store.categories())
        self.category_input.setCurrentText(event.category if event else "Работа")
        self.form.addRow("Категория", self.category_input)
        self.kind_input = QComboBox()
        self.kind_input.addItem("Постфактум — вне плана", "actual")
        self.kind_input.addItem("Запланировать локально", "planned")
        self.kind_input.setCurrentIndex(1 if event and event.current_start else 0)
        self.kind_input.setEnabled(event is None)
        self.form.addRow("Тип записи", self.kind_input)
        self.kind_note = plain_label("", "Muted")
        self.kind_note.setWordWrap(True)
        self.kind_note.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self.form.addRow("", self.kind_note)
        initial_start = (event.current_start or event.actual_start) if event else start.isoformat()
        initial_end = (event.current_end or event.actual_end) if event else (start + timedelta(minutes=30)).isoformat()
        self.start_input = self.date_edit(initial_start)
        self.end_input = self.date_edit(initial_end)
        self.start_label, self.end_label = plain_label(), plain_label()
        self.form.addRow(self.start_label, self.start_input)
        self.form.addRow(self.end_label, self.end_input)
        self.status_input = QComboBox()
        for key, label in STATUSES.items():
            self.status_input.addItem(label, key)
        self.status_input.setCurrentIndex(self.status_input.findData(event.status if event else "done"))
        self.form.addRow("Статус", self.status_input)
        self.fact_checkbox = QCheckBox("Указать фактическое время")
        self.fact_checkbox.setChecked(bool(event and event.actual_start))
        self.form.addRow("", self.fact_checkbox)
        self.fact_start = self.date_edit(event.actual_start if event and event.actual_start else initial_start)
        self.fact_end = self.date_edit(event.actual_end if event and event.actual_end else initial_end)
        self.form.addRow("Факт: начало", self.fact_start)
        self.form.addRow("Факт: конец", self.fact_end)
        self.fact_checkbox.toggled.connect(self._fact_enabled)
        self.note_input = QPlainTextEdit(event.note if event else "")
        self.note_input.setPlaceholderText("Результат, причина появления вне плана или другие подробности")
        self.note_input.setMaximumHeight(100)
        self.form.addRow("Комментарий", self.note_input)
        if event and event.baseline_start:
            baseline = plain_label("Исходный план зафиксирован и останется без изменений.", "Muted")
            baseline.setWordWrap(True)
            self.form.addRow("", baseline)
        self.error_label = plain_label("", "DangerText")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        outer.addWidget(self.error_label)
        actions = QHBoxLayout()
        if event:
            self.delete_button = QPushButton("Удалить событие")
            self.delete_button.setObjectName("Danger")
            self.delete_button.setEnabled(not event.baseline_start)
            self.delete_button.setToolTip("Событие зафиксированного плана можно отменить, сохранив исходный план."
                                          if event.baseline_start else "Удалить эту локальную запись с сохранением истории")
            self.delete_button.clicked.connect(self.delete)
            actions.addWidget(self.delete_button)
        actions.addStretch()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.save_button = buttons.button(QDialogButtonBox.StandardButton.Save)
        self.save_button.setText("Сохранить" if event else "Создать")
        self.save_button.setObjectName("Primary")
        self.save_button.setEnabled(bool(self.title_input.text().strip()))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        self.title_input.textChanged.connect(lambda value: self.save_button.setEnabled(bool(value.strip())))
        actions.addWidget(buttons)
        outer.addLayout(actions)
        self.kind_input.currentIndexChanged.connect(self._kind_changed)
        self._kind_changed()
        self.title_input.setFocus()

    @staticmethod
    def date_edit(value):
        stamp = datetime.fromisoformat(value)
        control = QDateTimeEdit()
        control.setDisplayFormat("dd.MM.yyyy HH:mm")
        install_date_picker(control)
        control.setDateTime(QDateTime(QDate(stamp.year, stamp.month, stamp.day),
                                      QTime(stamp.hour, stamp.minute, stamp.second)))
        return control

    @staticmethod
    def stamp(control):
        return control.dateTime().toString("yyyy-MM-dd'T'HH:mm:ss")

    def _fact_enabled(self):
        self.fact_start.setEnabled(self.fact_checkbox.isChecked())
        self.fact_end.setEnabled(self.fact_checkbox.isChecked())

    def _kind_changed(self):
        planned = self.kind_input.currentData() == "planned"
        self.start_label.setText("План: начало" if planned else "Факт: начало")
        self.end_label.setText("План: конец" if planned else "Факт: конец")
        self.kind_note.setText("Попадёт в исходный план только при его фиксации. Факт заполняется отдельно."
                               if planned else "Будет учтено вне плана. Даже последующая фиксация дня не добавит его в исходный план.")
        for field in (self.fact_checkbox, self.fact_start, self.fact_end):
            self.form.setRowVisible(field, planned)
        self._fact_enabled()
        if self._event is None:
            self.status_input.setCurrentIndex(self.status_input.findData("pending" if planned else "done"))

    def save(self):
        if self._saved:
            return
        planned = self.kind_input.currentData() == "planned"
        data = dict(title=self.title_input.text(), category=self.category_input.currentText(),
                    status=self.status_input.currentData(), note=self.note_input.toPlainText(),
                    actual_start=None, actual_end=None)
        if planned:
            data.update(current_start=self.stamp(self.start_input), current_end=self.stamp(self.end_input))
            if self.fact_checkbox.isChecked():
                data.update(actual_start=self.stamp(self.fact_start), actual_end=self.stamp(self.fact_end))
        else:
            data.update(actual_start=self.stamp(self.start_input), actual_end=self.stamp(self.end_input))
        try:
            if self._event:
                self.store.update_event(self._event.id, expected_revision=self._event.revision, **data)
            else:
                self.event_id = self.store.create_event(**data)
            self._saved = True
            self.accept()
        except Exception as exc:
            self.error_label.setText(str(exc))
            self.error_label.show()

    def delete(self):
        if not self._event or self._saved:
            return
        if QMessageBox.question(self, "Удалить локальное событие?",
                                f"Удалить «{self._event.title}»? Запись об удалении останется в истории.",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.store.delete_event(self._event.id, expected_revision=self._event.revision)
            self.event_id = None
            self._saved = True
            self.accept()
        except Exception as exc:
            self.error_label.setText(str(exc))
            self.error_label.show()
