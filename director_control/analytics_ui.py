"""Native period dashboard, shared by the light and dark desktop themes."""
from __future__ import annotations

from datetime import date, timedelta
from html import escape

from PySide6.QtCore import QDate, QRectF, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDateEdit, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QHeaderView, QMessageBox, QPushButton, QScrollArea,
    QSizePolicy, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from .i18n import decimal_text, tr
from .analytics import export_report, period_bounds
from .calendar_view import text
from .date_picker import install_date_picker
from .inspector import CategoryBars, plain_label
from .storage import STATUSES, category_label
from .event_status import FAILED_STATUSES, outcome_day
from .theme import color


def numeric(value):
    return decimal_text(f'{value:.1f}'.rstrip('0').rstrip('.'))


def duration(seconds):
    return tr("{0} ч").format(numeric(seconds / 3600))


def delta(minutes):
    if minutes is None:
        return '—'
    if not minutes:
        return tr('0 мин')
    return ('+' if minutes > 0 else '−') + (numeric(abs(minutes)) if abs(minutes) >= .05 else decimal_text('<0.1')) + tr(' мин')


def percent(value, lower=False):
    return '—' if value is None else ('≥ ' if lower else '') + numeric(value) + '%'


class AnalyticsMetric(QFrame):
    clicked = Signal()

    def __init__(self, title, actionable=False):
        super().__init__()
        self.setObjectName('Metric')
        self.setMinimumHeight(104)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(5)
        caption = plain_label(title, 'CardTitle')
        caption.setWordWrap(True)
        layout.addWidget(caption)
        self.value, self.note = plain_label('—', 'CardValue'), plain_label('', 'Muted')
        self.note.setWordWrap(True)
        layout.addWidget(self.value)
        layout.addWidget(self.note)
        self.actionable = actionable
        if actionable:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setToolTip(tr('Нажми, чтобы открыть соответствующий список событий'))
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            self.setAccessibleName(title + tr('. Открыть список событий'))

    def mouseReleaseEvent(self, event):
        if self.actionable and event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if self.actionable and event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space}:
            self.clicked.emit()
        else:
            super().keyPressEvent(event)

    def set_values(self, value, note):
        self.value.setText(value)
        self.note.setText(note)


class DailyBars(QWidget):
    day_selected = Signal(object)

    def __init__(self):
        super().__init__()
        self.report = None
        self.hit_areas = []
        self.setMinimumHeight(260)
        self.setMouseTracking(True)

    def set_report(self, report):
        self.report = report
        self.hit_areas = []
        self.setToolTip('')
        self.unsetCursor()
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), color('surface'))
        self.hit_areas = []
        if not self.report:
            p.end()
            return
        values = list(self.report.daily.items())
        maximum = max((max(m.planned_seconds, m.actual_seconds) / 3600 for _, m in values), default=0)
        if not maximum:
            text(p, QRectF(24, 95, self.width() - 48, 60), tr('Нет заполненных интервалов времени за этот период'), 12, color('muted'))
            p.end()
            return
        maximum = max(1., maximum * 1.1)
        plot = QRectF(50, 20, max(1, self.width() - 72), max(1, self.height() - 65))
        for tick in range(5):
            y = plot.bottom() - plot.height() * tick / 4
            p.setPen(color('grid'))
            p.drawLine(int(plot.left()), int(y), int(plot.right()), int(y))
            text(p, QRectF(1, y - 10, 43, 20), numeric(maximum * tick / 4) + tr(' ч'), 9, color('muted'))
        cell = plot.width() / len(values)
        width = min(22., cell * .28)
        label_step = max(1, (len(values) + 11) // 12)
        for i, (day, metrics) in enumerate(values):
            x = plot.left() + cell * (i + .5)
            for offset, seconds, token in ((-width - 1, metrics.planned_seconds, 'plan_bar'),
                                           (1, metrics.actual_seconds, 'actual_bar')):
                h = seconds / 3600 / maximum * plot.height()
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(color(token))
                p.drawRoundedRect(QRectF(x + offset, plot.bottom() - h, width, h), 2, 2)
                if token == 'actual_bar' and metrics.unplanned_seconds:
                    h = metrics.unplanned_seconds / 3600 / maximum * plot.height()
                    p.setBrush(color('unplanned_bar'))
                    p.drawRoundedRect(QRectF(x + offset, plot.bottom() - h, width, h), 2, 2)
            if i % label_step == 0 or i == len(values) - 1:
                label = day.strftime('%d.%m') if len(values) <= 7 else str(day.day)
                text(p, QRectF(x - 24, plot.bottom() + 8, 48, 22), label, 10, color('muted'))
            self.hit_areas.append((QRectF(plot.left() + i * cell, plot.top(), cell, plot.height() + 32), day))
        p.end()

    def _day_at(self, point):
        return next((d for rect, d in self.hit_areas if rect.contains(point)), None)

    def mouseMoveEvent(self, event):
        day = self._day_at(event.position())
        if day:
            m = self.report.daily[day]
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setToolTip(tr("{0:%d.%m.%Y}\nПлан: {1}\nФакт: {2}\nВне плана: {3}\nНажми, чтобы открыть события дня").format(day, duration(m.planned_seconds), duration(m.actual_seconds), duration(m.unplanned_seconds)))
        else:
            self.unsetCursor()
            self.setToolTip('')
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self.unsetCursor()
        self.setToolTip('')
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        day = self._day_at(event.position())
        if day and event.button() == Qt.MouseButton.LeftButton:
            self.day_selected.emit(day)
        super().mouseReleaseEvent(event)


def make_table(headers):
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
    table.setAlternatingRowColors(True)
    table.verticalHeader().hide()
    table.verticalHeader().setDefaultSectionSize(42)
    table.setMinimumWidth(0)
    table.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
    table.setMinimumHeight(260)
    return table


class AnalyticsPage(QScrollArea):
    open_requested = Signal(int)

    def __init__(self, store, anchor: date):
        super().__init__()
        self.store, self.report, self.dirty = store, None, True
        self.event_rows, self.day_filter = [], None
        self.mode = store.get_setting('ui_analytics_mode', 'week')
        if self.mode not in {'day', 'week', 'month'}:
            self.mode = 'week'
        self.setWidgetResizable(True)
        content = QWidget()
        content.setMinimumWidth(0)
        content.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 8, 8)
        layout.setSpacing(14)

        toolbar = QHBoxLayout()
        segments = QFrame()
        segments.setObjectName('Segments')
        segment_layout = QHBoxLayout(segments)
        segment_layout.setContentsMargins(3, 3, 3, 3)
        segment_layout.setSpacing(1)
        self.mode_buttons, self.mode_group = {}, QButtonGroup(self)
        for key, title in (('day', tr('День')), ('week', tr('Неделя')), ('month', tr('Месяц'))):
            button = QPushButton(title)
            button.setObjectName('Segment')
            button.setCheckable(True)
            button.setChecked(key == self.mode)
            button.clicked.connect(lambda checked, key=key: self.set_mode(key))
            self.mode_buttons[key] = button
            self.mode_group.addButton(button)
            segment_layout.addWidget(button)
        toolbar.addWidget(segments)
        toolbar.addStretch()
        for label, step in (('‹', -1), ('›', 1)):
            button = QPushButton(label)
            button.setObjectName('Arrow')
            button.setAccessibleName(tr('Предыдущий период') if step < 0 else tr('Следующий период'))
            button.clicked.connect(lambda checked=False, step=step: self.shift(step))
            toolbar.addWidget(button)
        today = QPushButton(tr('Сегодня'))
        today.clicked.connect(lambda: self.set_anchor(date.today()))
        toolbar.addWidget(today)
        self.date_input = QDateEdit(QDate(anchor.year, anchor.month, anchor.day))
        self.date_input.setMaximumDate(QDate(9998, 12, 31))
        self.date_input.setDisplayFormat('dd.MM.yyyy')
        self.date_input.setFixedWidth(126)
        install_date_picker(self.date_input)
        self.date_input.dateChanged.connect(self._changed)
        toolbar.addWidget(self.date_input)
        self.export_button = QPushButton('CSV')
        self.export_button.setToolTip(tr('Экспорт сводки и дней за весь выбранный период'))
        self.export_button.clicked.connect(self.export)
        toolbar.addWidget(self.export_button)
        layout.addLayout(toolbar)
        self.range_title = plain_label('', 'PeriodTitle')
        layout.addWidget(self.range_title)
        scope = QHBoxLayout()
        self.only_tracked = QCheckBox(tr('Только контролируемые категории'))
        self.only_tracked.setChecked(store.get_setting('ui_analytics_only_tracked', '1') == '1')
        self.only_tracked.toggled.connect(self._scope_changed)
        scope.addWidget(self.only_tracked)
        scope.addStretch()
        self.rules_button = QPushButton(tr('Как считаем'))
        self.rules_button.setCheckable(True)
        scope.addWidget(self.rules_button)
        layout.addLayout(scope)
        self.rules = plain_label(
            tr('Исполнение: выполненные события / исходный зафиксированный план; проценты дней не усредняются. '
            'Время: только заполненный факт со статусом «Выполнено» или «Частично», обрезанный границами периода. '
            'При выборе «Выполнено» пустой факт заполняется текущим временем события; его можно исправить. '
            '«Частично» без факта ожидает заполнения. '
            'Отмены и провалы считаются отдельно, включая дни без фиксации плана, по исходной дате, иначе текущей. '
            'У провала причину выбирает пользователь: ассистент или директор. Часы провалов не учитываются. '
            'Вне плана: локальные события постфактум и события, добавленные после фиксации их дня. '
            'Перенос зафиксированного события остаётся плановой работой. Если план не зафиксирован, происхождение '
            'работы неизвестно, а доля внепланового показана как нижняя граница (≥). '
            'Отклонения: факт минус исходное начало и длительность; в сводке — средние абсолютные значения '
            'по событиям с началом факта в периоде. Точный допуск включён в норму. '
            'Задачи исходного плана относятся к дате его начала; отсутствие факта — к исходной, иначе текущей дате. '
            'События на весь день не создают 24 часа и не требуют времени. '
            'Для зафиксированных событий контроль, категория плана и допуск берутся на момент фиксации.'), 'Muted')
        self.rules.setWordWrap(True)
        self.rules.hide()
        self.rules_button.toggled.connect(self.rules.setVisible)
        layout.addWidget(self.rules)
        self.quality = plain_label('', 'Muted')
        self.quality.setWordWrap(True)
        layout.addWidget(self.quality)
        grid = QGridLayout()
        grid.setSpacing(10)
        self.cards = {}
        for i, (key, title) in enumerate((('completion', tr('Исполнение исходного плана')),
                                         ('unplanned', tr('Доля внеплановой работы')),
                                         ('missing', tr('Ожидают фактического времени')),
                                         ('actual', tr('Подтверждённое время')),
                                         ('start', tr('Отклонение начала · среднее |Δ|')),
                                         ('duration', tr('Отклонение длительности · |Δ|')))):
            card = AnalyticsMetric(title, key == 'missing')
            self.cards[key] = card
            grid.addWidget(card, i // 3, i % 3)
            grid.setColumnStretch(i % 3, 1)
        self.cards['missing'].clicked.connect(self.show_missing)
        layout.addLayout(grid)
        outcomes = QHBoxLayout()
        for key, title in (('cancelled', tr('Отменено')), ('failed', tr('Провалено'))):
            card = AnalyticsMetric(title, True)
            self.cards[key] = card
            outcomes.addWidget(card, 1)
        self.cards['cancelled'].clicked.connect(self.show_cancelled)
        self.cards['failed'].clicked.connect(self.show_failed)
        layout.addLayout(outcomes)

        self.details = QTabWidget()
        self.details.setObjectName('AnalyticsDetails')
        self.details.setMinimumWidth(0)
        self.details.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        self.details.setMinimumHeight(380)
        dynamics = QWidget()
        dv = QVBoxLayout(dynamics)
        legend = QHBoxLayout()
        for title, token in ((tr('Исходный план'), 'PlanLegend'), (tr('Факт'), 'ActualLegend'), (tr('Вне плана'), 'UnplannedLegend')):
            legend.addWidget(plain_label('●  ' + title, token))
        legend.addStretch()
        dv.addLayout(legend)
        self.daily_bars = DailyBars()
        self.daily_bars.day_selected.connect(self.show_day)
        dv.addWidget(self.daily_bars, 1)
        self.details.addTab(dynamics, tr('Динамика'))
        self.day_table = make_table([tr('День'), tr('В плане'), tr('Выполнено'), tr('Исполнение'), tr('План, ч'), tr('Факт, ч'), tr('Вне плана'), tr('Отменено'), tr('Провалено')])
        self.day_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.day_table.activated.connect(lambda index: self.show_day(list(self.report.daily)[index.row()]) if self.report else None)
        self.details.addTab(self.day_table, tr('По дням'))
        categories = QWidget()
        cv = QVBoxLayout(categories)
        self.category_bars = CategoryBars()
        category_scroll = QScrollArea()
        category_scroll.setWidgetResizable(True)
        category_scroll.setWidget(self.category_bars)
        cv.addWidget(category_scroll, 1)
        self.category_table = make_table([tr('Категория'), tr('Исходный план, мин'), tr('Подтверждённый факт, мин')])
        self.category_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.category_table.setMinimumHeight(150)
        cv.addWidget(self.category_table)
        self.details.addTab(categories, tr('Категории'))
        events = QWidget()
        ev = QVBoxLayout(events)
        filters = QHBoxLayout()
        self.event_filter = QComboBox()
        for title, key in ((tr('Все события'), 'all'), (tr('Ожидают фактического времени'), 'missing'),
                           (tr('Отменено'), 'cancelled'), (tr('Провалено — все причины'), 'failed'),
                           (tr('Провалено · ассистент'), 'failed_assistant'), (tr('Провалено · директор'), 'failed_director'),
                           (tr('Внеплановая работа'), 'unplanned'), (tr('Отклонения вне допуска'), 'deviation'),
                           (tr('Без зафиксированного плана'), 'unfixed')):
            self.event_filter.addItem(title, key)
        self.event_filter.currentIndexChanged.connect(self._fill_events)
        filters.addWidget(self.event_filter)
        self.reset_day = QPushButton(tr('Весь период'))
        self.reset_day.clicked.connect(self.clear_day)
        self.reset_day.hide()
        filters.addWidget(self.reset_day)
        filters.addStretch()
        ev.addLayout(filters)
        self.events_note = plain_label(tr('Двойной щелчок или Enter — открыть карточку события'), 'Muted')
        self.events_note.setWordWrap(True)
        ev.addWidget(self.events_note)
        self.event_table = make_table([tr('Событие'), tr('Дата'), tr('Статус'), tr('Работа'), tr('План / факт\nмин'),
                                       tr('Начало\nΔ мин'), tr('Длительность\nΔ мин'), tr('Допуск\nмин'), tr('Учёт времени')])
        self.event_table.horizontalHeader().setFixedHeight(52)
        self.event_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for i, width in enumerate((240, 98, 195, 145, 115, 105, 120, 85, 165)):
            self.event_table.setColumnWidth(i, width)
        self.event_table.activated.connect(self._open_event)
        ev.addWidget(self.event_table, 1)
        self.details.addTab(events, tr('События'))
        layout.addWidget(self.details, 1)

    @property
    def anchor(self):
        return self.date_input.date().toPython()

    def set_anchor(self, day, refresh=True):
        if isinstance(day, QDate):
            day = day.toPython()
        self.date_input.blockSignals(True)
        self.date_input.setDate(QDate(day.year, day.month, day.day))
        self.date_input.blockSignals(False)
        self.dirty = True
        if refresh:
            self.refresh()

    def set_mode(self, mode):
        self.mode = mode
        self.mode_buttons[mode].setChecked(True)
        self.store.set_setting('ui_analytics_mode', mode)
        self.day_filter = None
        self.refresh()

    def shift(self, step):
        qdate = self.date_input.date()
        self.date_input.setDate(qdate.addMonths(step) if self.mode == 'month' else qdate.addDays(step * (7 if self.mode == 'week' else 1)))

    def _changed(self, *_):
        self.day_filter = None
        self.refresh()

    def _scope_changed(self, checked):
        self.store.set_setting('ui_analytics_only_tracked', '1' if checked else '0')
        self.refresh()

    def refresh(self):
        start, end = period_bounds(self.anchor, self.mode)
        self.range_title.setText(start.strftime('%d.%m.%Y') if self.mode == 'day' else
                                 f'{start:%d.%m.%Y} — {end - timedelta(days=1):%d.%m.%Y}')
        try:
            self.report = self.store.analytics_report(self.anchor, self.mode, self.only_tracked.isChecked())
        except Exception as exc:
            from .diagnostics import record_error
            record_error('analytics.calculate', exc)
            self.report = None
            self.quality.setText(tr('Не удалось рассчитать аналитику: ') + str(exc))
            for card in self.cards.values():
                card.set_values('—', '')
            for table in (self.day_table, self.category_table, self.event_table):
                table.setRowCount(0)
            self.category_bars.set_values([])
            self.event_rows = []
            self.events_note.setText(tr('Отчёт недоступен'))
            self.reset_day.hide()
            self.daily_bars.set_report(None)
            self.export_button.setEnabled(False)
            self.dirty = True
            return
        self.dirty = False
        self.export_button.setEnabled(True)
        r, m = self.report, self.report.totals
        self.cards['completion'].set_values(percent(m.completion_percent), tr("{0} из {1} событий\nЧастично: {2} · перенесено: {3}").format(m.done, m.planned, m.partial, m.moved))
        self.cards['unplanned'].set_values(percent(m.unplanned_percent, bool(m.unknown_seconds)), tr("{0} из {1} факта\nДоля по времени").format(duration(m.unplanned_seconds), duration(m.actual_seconds)))
        self.cards['missing'].set_values(str(m.missing_time), tr('Частично и ранее выполненные без факта\nНажми для заполнения'))
        self.cards['cancelled'].set_values(str(m.cancelled_total), tr("Из исходного плана: {0}\nНажми, чтобы открыть события").format(m.cancelled))
        self.cards['failed'].set_values(str(m.failed_total), tr("Ассистент: {0} · директор: {1}\nИз исходного плана: {2}").format(m.failed_assistant_total, m.failed_director_total, m.failed))
        self.cards['actual'].set_values(duration(m.actual_seconds), tr("Исходный план: {0}\nТолько выполнено и частично").format(duration(m.planned_seconds)))
        for key, value, outside in (('start', m.mean_start_minutes, m.start_outside), ('duration', m.mean_duration_minutes, m.duration_outside)):
            self.cards[key].set_values('—' if value is None else numeric(value) + tr(' мин'), tr("Сравнимых событий: {0}\nВне допуска: {1}").format(m.comparable, outside))
        parts = [tr("План зафиксирован: {0} из {1} дней").format(r.frozen_days, len(r.daily))]
        if r.loaded_days is not None:
            parts.append(tr("Полная загрузка Mail.ru: {0} из {1} дней").format(r.loaded_days, len(r.daily)))
        if m.unknown_seconds:
            parts.append(tr("Происхождение {0} факта неизвестно: план не зафиксирован. ≥ — нижняя граница доли внепланового").format(duration(m.unknown_seconds)))
        if m.overlap_seconds:
            parts.append(tr("Факт пересекается: {0} мин учтено повторно при суммировании событий").format(numeric(m.overlap_seconds / 60)))
        if r.source_warnings:
            parts.append(tr("Проверить состояние в Mail.ru: {0} событий").format(r.source_warnings))
        self.quality.setText(' · '.join(parts))
        self.daily_bars.set_report(r)
        self.day_table.setRowCount(len(r.daily))
        for row, (day, metrics) in enumerate(r.daily.items()):
            values = (day.strftime('%d.%m'), str(metrics.planned), str(metrics.done), percent(metrics.completion_percent),
                      numeric(metrics.planned_seconds / 3600), numeric(metrics.actual_seconds / 3600),
                      percent(metrics.unplanned_percent, bool(metrics.unknown_seconds)),
                      str(metrics.cancelled_total), str(metrics.failed_total))
            for col, value in enumerate(values):
                self.day_table.setItem(row, col, QTableWidgetItem(value))
            self.day_table.item(row, 8).setToolTip(tr("Ассистент: {0} · директор: {1}").format(metrics.failed_assistant_total, metrics.failed_director_total))
        categories = [(category_label(name), plan, fact) for name, plan, fact in r.categories]
        self.category_bars.set_values(categories)
        self.category_table.setRowCount(len(categories))
        for row, (name, plan, fact) in enumerate(categories):
            for col, value in enumerate((name, numeric(plan), numeric(fact))):
                self.category_table.setItem(row, col, QTableWidgetItem(value))
        if self.day_filter not in r.daily:
            self.day_filter = None
        self._fill_events()

    def show_missing(self):
        self.show_events('missing')

    def show_cancelled(self):
        self.show_events('cancelled')

    def show_failed(self):
        self.show_events('failed')

    def show_events(self, kind='all'):
        self.day_filter = None
        self.event_filter.setCurrentIndex(self.event_filter.findData(kind))
        self._fill_events()
        self.details.setCurrentIndex(3)
        self.ensureWidgetVisible(self.details)

    def show_day(self, day):
        self.day_filter = day
        self.event_filter.setCurrentIndex(self.event_filter.findData('all'))
        self._fill_events()
        self.details.setCurrentIndex(3)
        self.ensureWidgetVisible(self.details)

    def clear_day(self):
        self.day_filter = None
        self._fill_events()

    def _fill_events(self, *_):
        self.event_rows = []
        if not self.report:
            self.event_table.setRowCount(0)
            return
        kind = self.event_filter.currentData()
        for row in self.report.events:
            if kind == 'missing' and not row.missing_time:
                continue
            if kind in {'unplanned', 'unfixed'} and (row.origin != kind or not row.actual_seconds):
                continue
            if kind == 'deviation' and not (row.in_comparison and row.outside_tolerance):
                continue
            e = row.event
            if kind in FAILED_STATUSES | {'cancelled', 'failed'}:
                statuses = FAILED_STATUSES if kind == 'failed' else {kind}
                day = outcome_day(e)
                if e.status not in statuses or not day or not self.report.start.isoformat() <= day < self.report.end.isoformat():
                    continue
                if self.day_filter and day != self.day_filter.isoformat():
                    continue
            if self.day_filter:
                ds, de = self.day_filter.isoformat() + 'T00:00:00', (self.day_filter + timedelta(days=1)).isoformat() + 'T00:00:00'
                if not any(s and end and s < de and end > ds for s, end in
                           ((e.baseline_start, e.baseline_end), (e.current_start, e.current_end), (e.actual_start, e.actual_end))):
                    continue
            self.event_rows.append(row)
        self.event_table.setRowCount(len(self.event_rows))
        self.reset_day.setVisible(self.day_filter is not None)
        self.events_note.setText((f'{self.day_filter:%d.%m.%Y} · ' if self.day_filter else '') +
                                tr("Событий: {0}. Двойной щелчок или Enter — открыть карточку").format(len(self.event_rows)))
        origins = {'planned': tr('По исходному плану'), 'unplanned': tr('Вне плана'), 'unfixed': tr('План не зафиксирован')}
        for i, row in enumerate(self.event_rows):
            e = row.event
            day = (e.actual_start or e.baseline_start or e.current_start or '')[:10]
            if e.status in FAILED_STATUSES | {'cancelled'}:
                day = outcome_day(e)
            timing = tr('Не заполнено') if row.missing_time else tr('Факт подтверждён') if row.actual_seconds else tr('Весь день') if row.all_day else tr('Нет факта в периоде')
            values = (e.title, date.fromisoformat(day).strftime('%d.%m.%Y') if day else '—', tr(STATUSES[e.status]),
                      origins[row.origin], numeric(row.planned_seconds / 60) + ' / ' + numeric(row.actual_seconds / 60),
                      delta(row.start_delta), delta(row.duration_delta), str(row.tolerance) if row.start_delta is not None else '—', timing)
            tooltip = '<br>'.join(escape(line) for line in (
                e.title, tr('Исходный план: ') + self._span(e.baseline_start, e.baseline_end),
                tr('Актуальный план: ') + self._span(e.current_start, e.current_end),
                tr('Факт: ') + self._span(e.actual_start, e.actual_end),
                tr("Категория плана: {0}; текущая: {1}").format(category_label(row.baseline_category), category_label(e.category)),
                tr('Δ начала: плюс — позже, минус — раньше. Δ длительности: плюс — дольше, минус — короче.'),
                tr('Средние отклонения: ') + (tr('участвует') if row.in_comparison else tr('не участвует (нет сравнения или начало факта вне периода)')),
                tr('Минуты в таблице ограничены периодом; отклонения рассчитаны по полным интервалам.'),
                row.source_warning, e.note) if line)
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(tooltip)
                deviation = row.start_delta if col == 5 else row.duration_delta if col == 6 else None
                if deviation is not None and abs(deviation) > row.tolerance:
                    item.setForeground(color('danger'))
                self.event_table.setItem(i, col, item)

    @staticmethod
    def _span(start, end):
        return f'{start.replace("T", " ")} — {end.replace("T", " ")}' if start and end else tr('не заполнено')

    def _open_event(self, index):
        if 0 <= index.row() < len(self.event_rows):
            self.open_requested.emit(self.event_rows[index.row()].event.id)

    def export(self):
        if not self.report:
            return
        path, _ = QFileDialog.getSaveFileName(self, tr('Экспорт аналитики за период'),
                    f'analytics-{self.report.start}-{self.report.end - timedelta(days=1)}.csv', 'CSV (*.csv)')
        if path:
            try:
                export_report(self.report, path)
            except Exception as exc:
                from .diagnostics import record_error
                record_error('analytics.export', exc)
                QMessageBox.warning(self, tr('Не удалось сохранить аналитику'), str(exc))

