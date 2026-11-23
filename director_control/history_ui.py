"""Search and browse the complete local journal without loading it into a table."""
from datetime import date
from html import escape

from PySide6.QtCore import QDate, QTimer, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QCompleter, QDateEdit, QDialog, QDialogButtonBox,
    QFrame, QHBoxLayout, QHeaderView, QLineEdit, QPlainTextEdit, QPushButton,
    QSizePolicy, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .widget_text import Message, add_choice, localized, set_headers
from .i18n import tr
from .date_picker import install_date_picker
from .history import describe, display_time, history_title
from .inspector import plain_label, text_label


SHORT_ACTIONS = {'Изменение': 'Данные изменены', 'Фиксация плана': 'План зафиксирован'}


def number(value):
    return f'{value:,}'.replace(',', ' ')


class HistoryEntryDialog(QDialog):
    def __init__(self, store, record, parent=None):
        super().__init__(parent)
        self.requested_event = None
        self.setWindowTitle(tr('Запись истории'))
        self.resize(640, 440)
        self.setMinimumSize(460, 300)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(9)
        description = describe(record['action'], record['details'])
        metadata = f"{description.action}  ·  {display_time(record['changed_at'], seconds=True)}"
        for value, name in ((history_title(record['title'], record['action']), 'EventTitle'), (metadata, 'Muted')):
            label = plain_label(value, name)
            label.setWordWrap(True)
            layout.addWidget(label)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlainText(description.details)
        layout.addWidget(self.details, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText(tr('Закрыть'))
        buttons.rejected.connect(self.reject)
        self.open_button = buttons.addButton(tr('Открыть событие'), QDialogButtonBox.ButtonRole.ActionRole)
        exists = False
        if record['event_id'] is not None:
            try:
                exists = store.get_event(record['event_id']).source in {'local', 'caldav'}
            except KeyError:
                pass
        self.open_button.setEnabled(exists)
        if not exists:
            self.open_button.setToolTip(tr('Событие удалено, находится в архиве или запись относится к настройкам'))
        self.open_button.clicked.connect(lambda: self._open(record['event_id']))
        layout.addWidget(buttons)

    def _open(self, event_id):
        self.requested_event = event_id
        self.accept()


class HistoryPage(QWidget):
    open_requested = Signal(int)

    def __init__(self, store):
        super().__init__()
        self.store, self.dirty, self.page = store, True, None
        self.rows, self.cursors, self.page_index = [], [None], 0
        self.ceiling = None
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(300)
        self.timer.timeout.connect(self.apply_filters)

        search_row = QHBoxLayout()
        search_row.setSpacing(6)
        self.search = QLineEdit()
        localized(self.search, placeholderText='Поиск в истории', accessibleName='Поиск в истории',
                  toolTip='Поиск по названию, действию и описанию изменений')
        self.search.setClearButtonEnabled(True)
        self.search.setMaxLength(300)
        self.search.textChanged.connect(self.queue_filters)
        self.search.returnPressed.connect(self.apply_filters)
        search_row.addWidget(self.search, 1)
        self.filters_button = localized(QPushButton(), text='Фильтры')
        self.filters_button.setObjectName('HistoryFilters')
        self.filters_button.setCheckable(True)
        search_row.addWidget(self.filters_button)
        self.reset_button = localized(QPushButton(), text='Сбросить фильтры')
        self.reset_button.setObjectName('Link')
        self.reset_button.hide()
        self.reset_button.clicked.connect(self.reset_filters)
        search_row.addWidget(self.reset_button)
        self.refresh_button = localized(QPushButton(), text='Обновить')
        self.refresh_button.clicked.connect(self.refresh_latest)
        search_row.addWidget(self.refresh_button)
        layout.addLayout(search_row)

        self.filters_panel = QFrame()
        self.filters_panel.setObjectName('HistoryFiltersPanel')
        filters = QVBoxLayout(self.filters_panel)
        filters.setContentsMargins(12, 9, 12, 9)
        filters.setSpacing(6)
        self.filters_panel.hide()
        self.filters_button.toggled.connect(self.filters_panel.setVisible)
        layout.addWidget(self.filters_panel)
        event_row = QHBoxLayout()
        event_row.addWidget(text_label('Событие'))
        self.event_filter = QComboBox()
        localized(self.event_filter, accessibleName='Событие')
        self.event_filter.setEditable(True)
        self.event_filter.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.event_filter.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.event_filter.setMinimumContentsLength(18)
        self.event_filter.setMinimumWidth(0)
        self.event_filter.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.event_filter.setMaxVisibleItems(12)
        self.event_filter.lineEdit().setClearButtonEnabled(True)
        localized(self.event_filter.lineEdit(), placeholderText='Все события или часть названия')
        self.event_filter.addItem(tr('Все события и настройки'), None)
        self.event_filter.addItem(tr('Только настройки и обслуживание'), 'system')
        completer = self.event_filter.completer()
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.event_filter.editTextChanged.connect(self.queue_filters)
        self.event_filter.activated.connect(self.apply_filters)
        event_row.addWidget(self.event_filter, 1)
        self.selected_event_button = localized(QPushButton(), text='По выбранной записи')
        localized(self.selected_event_button, toolTip='Отфильтровать историю по событию из выбранной строки')
        self.selected_event_button.setEnabled(False)
        self.selected_event_button.clicked.connect(self.filter_selected_event)
        event_row.addWidget(self.selected_event_button)
        filters.addLayout(event_row)

        dates = QHBoxLayout()
        self.date_enabled = localized(QCheckBox(), text='Дата изменения')
        localized(self.date_enabled, toolTip='Фильтр по дате записи в истории, включая обе границы')
        self.date_enabled.toggled.connect(self.date_toggled)
        dates.addWidget(self.date_enabled)
        today = date.today()
        self.date_from = self._date_edit(today.replace(day=1))
        self.date_to = self._date_edit(today)
        for caption, control in (('С', self.date_from), ('По', self.date_to)):
            dates.addWidget(text_label(caption))
            localized(control, accessibleName=caption)
            dates.addWidget(control)
        dates.addStretch()
        filters.addLayout(dates)
        self.message = plain_label('', 'Muted')
        self.message.setWordWrap(True)
        self.message.hide()
        layout.addWidget(self.message)
        self.error = plain_label('', 'DangerText')
        self.error.setWordWrap(True)
        self.error.hide()
        layout.addWidget(self.error)

        self.table = QTableWidget(0, 4)
        self.table.setObjectName('HistoryTable')
        set_headers(self.table, ['Когда изменено', 'Событие / объект', 'Действие', 'Что изменилось'])
        self.table.setMinimumWidth(0)
        self.table.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        vertical_header = self.table.verticalHeader()
        vertical_header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        vertical_header.setDefaultSectionSize(38)
        vertical_header.hide()
        header = self.table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._summary_widths = None
        for column in (1, 3):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Stretch)
        self.table.activated.connect(self.open_record)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        localized(self.table, toolTip='Двойной щелчок или Enter — полное описание записи')
        self.empty = plain_label('', 'Muted')
        self.empty.setWordWrap(True)
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.empty.hide()
        empty_layout = QVBoxLayout(self.table.viewport())
        empty_layout.setContentsMargins(16, 8, 16, 8)
        empty_layout.addWidget(self.empty)
        layout.addWidget(self.table, 1)
        footer = QHBoxLayout()
        footer.setSpacing(6)
        self.count = text_label('История ещё не загружена', 'Muted')
        footer.addWidget(self.count)
        self.open_entry_button = localized(QPushButton(), text='Открыть запись')
        self.open_entry_button.setObjectName('Link')
        self.open_entry_button.clicked.connect(lambda: self.open_record(self.table.currentIndex()))
        self.open_entry_button.setEnabled(False)
        footer.addWidget(self.open_entry_button)
        footer.addStretch()
        self.first_button = localized(QPushButton(), text='К началу')
        self.first_button.clicked.connect(self.refresh_latest)
        self.newer_button = localized(QPushButton(), text='← Новее')
        self.newer_button.clicked.connect(self.go_newer)
        self.older_button = localized(QPushButton(), text='Старее →')
        self.older_button.clicked.connect(self.go_older)
        for button in (self.first_button, self.newer_button, self.older_button):
            button.setObjectName('HistoryPageButton')
            button.setEnabled(False)
            footer.addWidget(button)
        self.page_size = QComboBox()
        localized(self.page_size, accessibleName='Записей на странице', toolTip='Записей на странице')
        for size in (50, 100, 200):
            add_choice(self.page_size, Message("По {0}", size), size)
        saved = store.get_setting('ui_history_page_size', '100')
        self.page_size.setCurrentIndex({50: 0, 100: 1, 200: 2}.get(int(saved) if saved in {'50', '100', '200'} else 100, 1))
        self.page_size.currentIndexChanged.connect(self._size_changed)
        footer.addWidget(self.page_size)
        layout.addLayout(footer)

    def _date_edit(self, day):
        control = QDateEdit(QDate(day.year, day.month, day.day))
        control.setMaximumDate(QDate(9998, 12, 31))
        control.setDisplayFormat('dd.MM.yyyy')
        control.setFixedWidth(126)
        install_date_picker(control)
        control.setEnabled(False)
        control.dateChanged.connect(self.apply_filters)
        return control

    def date_toggled(self, checked):
        self.date_from.setEnabled(checked)
        self.date_to.setEnabled(checked)
        self.apply_filters()

    def queue_filters(self, *_):
        for button in (self.first_button, self.newer_button, self.older_button):
            button.setEnabled(False)
        self.timer.start()

    def _size_changed(self, *_):
        self.store.set_setting('ui_history_page_size', str(self.page_size.currentData()))
        self.apply_filters()

    def _event_choice(self):
        combo = self.event_filter
        if combo.currentText() == combo.itemText(combo.currentIndex()):
            return combo.currentData(), ''
        return None, combo.currentText().strip()

    def _load_event_options(self):
        event_id, typed = self._event_choice()
        combo = self.event_filter
        combo.blockSignals(True)
        try:
            combo.clear()
            combo.addItem(tr('Все события и настройки'), None)
            combo.addItem(tr('Только настройки и обслуживание'), 'system')
            for row in self.store.audit_event_options():
                suffix = tr(' · удалено') if row['deleted'] else tr(' · архив') if row['source'] == 'manual' else ''
                day = ' · ' + display_time(row['starts']) if row['starts'] else ''
                caption = f'{row["title"]}{day}{suffix} · №{row["event_id"]}'
                combo.addItem(caption, row['event_id'])
                combo.setItemData(combo.count() - 1, caption, Qt.ItemDataRole.ToolTipRole)
            combo.setCurrentIndex(max(0, combo.findData(event_id)))
            if typed:
                combo.setEditText(typed)
        finally:
            combo.blockSignals(False)

    def apply_filters(self, *_):
        self.timer.stop()
        self.cursors, self.page_index, self.ceiling = [None], 0, None
        self._load()

    def refresh(self):
        if not self.window().isEnabled():
            self.dirty = True
            return
        if self.timer.isActive():
            self.cursors, self.page_index, self.ceiling = [None], 0, None
        self.timer.stop()
        try:
            self._load_event_options()
        except Exception as exc:
            from .diagnostics import record_error
            record_error('history.load', exc)
            self._failed(exc)
            return
        # Keep older pages stable while new entries arrive. At the first page,
        # revisiting History naturally shows the latest records.
        if self.page_index == 0:
            self.ceiling = None
        self._load(preserve_view=self.page_index > 0)

    def refresh_latest(self, *_):
        self.timer.stop()
        self.cursors, self.page_index, self.ceiling = [None], 0, None
        self.refresh()

    def _fit_summary_columns(self):
        metrics = self.table.fontMetrics()
        # Two short cell margins keep full timestamps and everyday actions readable.
        timestamp_width = metrics.horizontalAdvance('00.00.0000 00:00:00') + 24
        action_width = max(metrics.horizontalAdvance(tr(label)) for label in SHORT_ACTIONS.values()) + 24
        if self._summary_widths != (timestamp_width, action_width):
            self._summary_widths = timestamp_width, action_width
            self.table.setColumnWidth(0, timestamp_width)
            self.table.setColumnWidth(2, action_width)

    def _load(self, preserve_view=False):
        if not self.window().isEnabled():
            self.dirty = True
            return
        self._fit_summary_columns()
        event_id, typed = self._event_choice()
        advanced = int(bool(event_id is not None or typed)) + int(self.date_enabled.isChecked())
        localized(self.filters_button, text=Message('Фильтры · {0}', advanced) if advanced else 'Фильтры')
        filtered = bool(advanced or self.search.text().strip())
        self.reset_button.setVisible(filtered)
        selected = self.table.currentRow()
        selected_id = self.rows[selected]['id'] if preserve_view and 0 <= selected < len(self.rows) else None
        scroll = self.table.verticalScrollBar().value() if preserve_view else 0
        try:
            page = self.store.audit_page(search=self.search.text(), event_id=event_id, event_search=typed,
                date_from=self.date_from.date().toPython() if self.date_enabled.isChecked() else None,
                date_to=self.date_to.date().toPython() if self.date_enabled.isChecked() else None,
                before_id=self.cursors[self.page_index], ceiling_id=self.ceiling,
                limit=self.page_size.currentData())
        except Exception as exc:
            from .diagnostics import record_error
            record_error('history.load', exc)
            self._failed(exc)
            return
        self.page, self.rows, self.ceiling, self.dirty = page, list(page.rows), page.ceiling_id, False
        self.error.hide()
        self.empty.setVisible(not page.total)
        self.empty.setText(tr('По выбранным условиям записей нет. Измени или сбрось фильтры.')
                           if filtered else tr('В истории пока нет записей'))
        self.table.setRowCount(len(self.rows))
        title_font = self.table.font()
        title_font.setWeight(QFont.Weight.DemiBold)
        for i, row in enumerate(self.rows):
            description = describe(row['action'], row['details'])
            for column, value in enumerate((display_time(row['changed_at'], seconds=True), history_title(row['title'], row['action']),
                                           description.action, description.details)):
                summary = tr(SHORT_ACTIONS[row['action']]) if column == 2 and row['action'] in SHORT_ACTIONS else value
                item = QTableWidgetItem(' · '.join(summary.splitlines()))
                if column == 1:
                    item.setFont(title_font)
                item.setToolTip('<qt>' + escape(value).replace('\n', '<br>') + '</qt>')
                self.table.setItem(i, column, item)
        self.table.clearSelection()
        self.table.setCurrentCell(-1, -1)
        self.selected_event_button.setEnabled(False)
        self.open_entry_button.setEnabled(False)
        if selected_id is not None:
            for i, row in enumerate(self.rows):
                if row['id'] == selected_id:
                    self.table.setCurrentCell(i, 0)
                    break
        self.table.verticalScrollBar().setValue(scroll)
        start = self.page_index * self.page_size.currentData() + 1 if self.rows else 0
        finish = start + len(self.rows) - 1 if self.rows else 0
        self.count.setText(tr("{0}–{1} из {2}").format(number(start), number(finish), number(page.total)))
        self.message.setVisible(bool(page.newer_count))
        if page.newer_count:
            self.message.setText(tr("Новых записей по фильтру: {0}. Нажми «Обновить», чтобы перейти к ним.").format(number(page.newer_count)))
        for button in (self.newer_button, self.older_button, self.first_button):
            button.setVisible(self.page_index > 0 or page.has_older or page.newer_count > 0)
        self.newer_button.setEnabled(self.page_index > 0)
        self.first_button.setEnabled(self.page_index > 0 or page.newer_count > 0)
        self.older_button.setEnabled(page.has_older)

    def _failed(self, exc):
        self.page, self.rows, self.dirty = None, [], True
        self.table.setRowCount(0)
        self.count.setText(tr('Записи не показаны'))
        self.message.hide()
        self.empty.hide()
        self.error.setText(str(exc))
        self.error.show()
        for button in (self.first_button, self.newer_button, self.older_button, self.selected_event_button, self.open_entry_button):
            button.setEnabled(False)

    def go_older(self):
        if not self.page or not self.page.has_older or self.timer.isActive():
            return
        cursor = self.rows[-1]['id']
        self.cursors = self.cursors[:self.page_index + 1] + [cursor]
        self.page_index += 1
        self._load()

    def go_newer(self):
        if self.page_index and not self.timer.isActive():
            self.page_index -= 1
            self._load()

    def reset_filters(self):
        controls = (self.search, self.event_filter, self.date_enabled, self.date_from, self.date_to)
        for control in controls:
            control.blockSignals(True)
        self.search.clear()
        self.event_filter.setCurrentIndex(0)
        self.event_filter.setEditText(self.event_filter.itemText(0))
        self.date_enabled.setChecked(False)
        for control in controls:
            control.blockSignals(False)
        self.date_from.setEnabled(False)
        self.date_to.setEnabled(False)
        self.apply_filters()

    def _selection_changed(self):
        row = self.table.currentRow()
        self.open_entry_button.setEnabled(0 <= row < len(self.rows))
        self.selected_event_button.setEnabled(0 <= row < len(self.rows) and self.rows[row]['event_id'] is not None)

    def filter_selected_event(self):
        row = self.table.currentRow()
        if 0 <= row < len(self.rows) and self.rows[row]['event_id'] is not None:
            index = self.event_filter.findData(self.rows[row]['event_id'])
            if index < 0:
                self._load_event_options()
                index = self.event_filter.findData(self.rows[row]['event_id'])
            if index >= 0:
                self.event_filter.setCurrentIndex(index)
                self.apply_filters()

    def open_record(self, index):
        if 0 <= index.row() < len(self.rows):
            dialog = HistoryEntryDialog(self.store, self.rows[index.row()], self)
            accepted = dialog.exec() == QDialog.DialogCode.Accepted
            event_id = dialog.requested_event
            dialog.deleteLater()
            if accepted and event_id is not None:
                self.open_requested.emit(event_id)

