"""Selected event details and compact analytics bars."""
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QFont, QPainter
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QWidget

from .i18n import decimal_text, tr
from .calendar_view import text
from .storage import STATUSES, category_label
from .source_state import source_state
from .theme import color as theme_color


def plain_label(value="", object_name=None):
    label = QLabel(value)
    label.setTextFormat(Qt.TextFormat.PlainText)
    if object_name:
        label.setObjectName(object_name)
    return label


class EventInspector(QFrame):
    edit_requested = Signal()
    done_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("Inspector")
        self.setFixedWidth(280)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 23, 20, 20)
        layout.setSpacing(14)
        layout.addWidget(plain_label(tr("В ФОКУСЕ"), "Eyebrow"))
        self.title = plain_label(tr("Выбери событие"), "EventTitle")
        self.title.setWordWrap(True)
        layout.addWidget(self.title)
        self.category = plain_label(tr("Нажми на встречу в календаре"), "Muted")
        self.category.setWordWrap(True)
        layout.addWidget(self.category)
        self.status = plain_label("", "StatusPill")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.time_labels = {}
        for key, title in (("baseline", tr("ИСХОДНЫЙ ПЛАН")), ("current", tr("АКТУАЛЬНОЕ ВРЕМЯ")), ("actual", tr("ФАКТ"))):
            layout.addWidget(plain_label(title, "Eyebrow"))
            value = plain_label("—")
            value.setWordWrap(True)
            self.time_labels[key] = value
            layout.addWidget(value)
        self.note = plain_label("", "Muted")
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        layout.addStretch()
        self.edit_button = QPushButton(tr("Открыть карточку"))
        self.edit_button.setObjectName("Primary")
        self.edit_button.clicked.connect(self.edit_requested)
        layout.addWidget(self.edit_button)
        self.done_button = QPushButton(tr("Отметить выполненным"))
        self.done_button.clicked.connect(self.done_requested)
        layout.addWidget(self.done_button)
        self.set_event(None)

    def set_event(self, event, info=None):
        from datetime import datetime, timedelta
        self.edit_button.setEnabled(event is not None)
        self.done_button.setEnabled(event is not None and event.status != "done")
        if event is None:
            self.title.setText(tr("Выбери событие"))
            self.category.setText(tr("Нажми на встречу, чтобы увидеть план и факт"))
            self.status.hide()
            self.note.setText("")
            for label in self.time_labels.values():
                label.setText("—")
            return
        self.title.setText(event.title)
        self.category.setText(category_label(event.category) + "  ·  " + event.source_label)
        status = tr(STATUSES[event.status])
        if event.is_postfactum:
            status = tr("Вне плана · ") + status
        state = source_state(event, info)
        if state.suffix:
            status += ' · ' + state.suffix
        self.status.setText(status)
        self.status.show()
        for key, (start, end) in {
            "baseline": (event.baseline_start, event.baseline_end), "current": (event.current_start, event.current_end),
            "actual": (event.actual_start, event.actual_end),
        }.items():
            if not start:
                value = (tr("Не планировалось") if event.is_postfactum and key in {"baseline", "current"}
                         else tr("Не зафиксирован") if key == "baseline" else tr("Не заполнен"))
            else:
                a, b = datetime.fromisoformat(start), datetime.fromisoformat(end)
                all_day = info and ((info.get("baseline_all_day") if key == "baseline" else info.get("all_day")) if key != "actual" else False)
                whole_day = (tr("{0:%d.%m} – {1:%d.%m} · весь день").format(a, b - timedelta(days=1))
                             if a.date() != (b - timedelta(days=1)).date() else tr("{0:%d.%m.%Y} · весь день").format(a))
                value = whole_day if all_day else (
                    f"{a:%d.%m} · {a:%H:%M} – {b:%H:%M}" if a.date() == b.date() else f"{a:%d.%m %H:%M} – {b:%d.%m %H:%M}")
            self.time_labels[key].setText(value)
        needs_fact = (event.status in {'done', 'partial'} and not event.actual_start
                      and not (info or {}).get('all_day'))
        self.note.setText('\n'.join(part for part in (event.note, tr('Ожидается фактическое время.') if needs_fact else '') if part))


class CategoryBars(QWidget):
    def __init__(self):
        super().__init__()
        self.values = []
        self.setMinimumHeight(250)

    def set_values(self, values):
        self.values = values
        self.setMinimumHeight(max(220, len(values) * 60 + 55))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), theme_color("surface"))
        text(p, QRectF(18, 7, self.width() - 36, 25), tr("Распределение времени · минуты"), 13, weight=QFont.Weight.DemiBold)
        if not self.values:
            text(p, QRectF(18, 80, self.width() - 36, 25), tr("Здесь появится сравнение плана и подтверждённого факта"), 12, theme_color("calendar_muted"))
        maximum = max((max(planned, actual) for _, planned, actual in self.values), default=1) or 1
        for i, (name, planned, actual) in enumerate(self.values):
            y = 44 + i * 60
            text(p, QRectF(18, y, 155, 20), name, 12)
            available = max(50, self.width() - 245)
            for offset, value, color in ((0, planned, "plan_bar"), (17, actual, "actual_bar")):
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(theme_color(color))
                if value:
                    p.drawRoundedRect(QRectF(180, y + offset + 2, available * value / maximum, 11), 4, 4)
                text(p, QRectF(185 + available * value / maximum, y + offset - 2, 55, 20), decimal_text(f"{value:.1f}".rstrip("0").rstrip(".")), 11, theme_color("muted"))
        p.end()
