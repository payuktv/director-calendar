"""Inspect the events behind the Mail.ru sync's review count."""
from datetime import datetime, timedelta
from html import escape

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHeaderView, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from .history import display_time
from .i18n import tr
from .inspector import text_label
from .storage import STATUSES
from .widget_text import set_headers


def _review_interval(item):
    event = item.event
    start = event.current_start or event.baseline_start or event.actual_start
    end = event.current_end or event.baseline_end or event.actual_end
    first, last = datetime.fromisoformat(start), datetime.fromisoformat(end)
    if item.all_day:
        last_day = last.date() - timedelta(days=1)
        short = tr('{0:%d.%m.%Y} · весь день').format(first)
        full = (f'{first:%d.%m.%Y} – {last_day:%d.%m.%Y} · ' + tr('Весь день')
                if last_day > first.date() else short)
    else:
        short = display_time(start)
        full = f'{short} – {display_time(end)}'
        if first.date() == last.date():
            short += f'–{last:%H:%M}'
    return short, full


class MailReviewDialog(QDialog):
    open_requested = Signal(int)

    def __init__(self, store, calendar_key, parent=None):
        super().__init__(parent)
        self.store = store
        self.calendar_key = calendar_key
        self.setWindowTitle(tr('События Mail.ru, требующие проверки'))
        self.resize(820, 400)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        self.table = QTableWidget(0, 4)
        set_headers(self.table, ['Дата и время', 'Событие', 'Статус в календаре', 'Причина проверки'])
        self.table.setAccessibleName(self.windowTitle())
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(36)
        header = self.table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)
        self.hint = text_label('Событие могло быть перенесено за пределы загруженного периода Mail.ru.', 'Muted')
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)
        self.empty = text_label('Событий для проверки нет')
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText(tr('Закрыть'))
        buttons.rejected.connect(self.reject)
        self.open_button = buttons.addButton(tr('Открыть событие'), QDialogButtonBox.ButtonRole.ActionRole)
        self.open_button.setAutoDefault(False)
        self.open_button.clicked.connect(self.open_selected)
        self.table.activated.connect(self.open_selected)
        self.table.itemSelectionChanged.connect(lambda: self.open_button.setEnabled(self.table.currentRow() >= 0))
        layout.addWidget(buttons)
        self.refresh()

    def open_selected(self):
        item = self.table.item(self.table.currentRow(), 1)
        if item is not None:
            self.open_requested.emit(item.data(Qt.ItemDataRole.UserRole))

    def refresh(self):
        previous_row = self.table.currentRow()
        selected = self.table.item(previous_row, 1)
        selected_id = selected.data(Qt.ItemDataRole.UserRole) if selected is not None else None
        items = self.store.mail_review_items(self.calendar_key)
        self.table.setRowCount(len(items))
        target_row = max(0, min(previous_row, len(items) - 1))
        for row, item in enumerate(items):
            event = item.event
            when, full_interval = _review_interval(item)
            reason = tr('Нет в ответе Mail.ru') if item.state.code == 'missing' else item.state.warning
            for column, value in enumerate((when, event.title, tr(STATUSES[event.status]), reason)):
                cell = QTableWidgetItem(value)
                cell.setToolTip('<qt>' + escape(full_interval if column == 0 else value) + '</qt>')
                if column == 1:
                    cell.setData(Qt.ItemDataRole.UserRole, event.id)
                self.table.setItem(row, column, cell)
            if event.id == selected_id:
                target_row = row
        self.table.setVisible(bool(items))
        self.empty.setVisible(not items)
        self.hint.setVisible(any(item.state.code == 'missing' for item in items))
        self.open_button.setEnabled(bool(items))
        if items:
            self.table.setCurrentCell(target_row, 1)
