"""Native, painted day/week/month calendar. No web runtime or external service."""
from __future__ import annotations

import hashlib
import math
from html import escape
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from PySide6.QtCore import QEvent, QPoint, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen, QTextLayout, QTextOption
from PySide6.QtWidgets import QScrollArea, QStackedWidget, QToolTip, QVBoxLayout, QWidget

from .storage import STATUSES

MONTHS = ("январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь")
MONTHS_GEN = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря")
WEEKDAYS = ("ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС")
ACCENT = QColor("#6956E8")
GRID = QColor("#EEF0F6")
TEXT = QColor("#373C52")
MUTED = QColor("#9296AB")
GUTTER = 52
HOUR = 66
STATUS_COLORS = {
    "cancelled": ("#BE7186", "#FCF0F3"),
    "done": ("#369A83", "#EDF8F4"),
    "partial": ("#A87900", "#FFF4C2"),
    "moved": ("#397ED8", "#EAF2FF"),
}


def period_days(focus: date, mode: str) -> list[date]:
    if mode == "week":
        start = focus - timedelta(days=focus.weekday())
        return [start + timedelta(days=i) for i in range(7)]
    if mode == "month":
        first = focus.replace(day=1)
        start = first - timedelta(days=first.weekday())
        return [start + timedelta(days=i) for i in range(42)]
    return [focus]


@dataclass(frozen=True)
class Block:
    event: object
    day: date
    start: float
    end: float
    lane: int = 0
    lanes: int = 1


def layout_overlaps(blocks: list[Block]) -> list[Block]:
    """Give simultaneous intervals separate lanes; adjacent intervals reuse one lane."""
    from dataclasses import replace
    result, group, lane_ends = [], [], []
    maximum = -1
    def flush():
        result.extend(replace(block, lanes=len(lane_ends)) for block in group)
    for block in sorted(blocks, key=lambda b: (b.start, -b.end, b.event.id)):
        if group and block.start >= maximum:
            flush()
            group, lane_ends = [], []
        lane = next((i for i, end in enumerate(lane_ends) if end <= block.start), len(lane_ends))
        if lane == len(lane_ends):
            lane_ends.append(block.end)
        else:
            lane_ends[lane] = block.end
        group.append(replace(block, lane=lane))
        maximum = max(b.end for b in group)
    if group:
        flush()
    return result


def event_interval(event, layer):
    fields = {"current": ("current_start", "current_end"), "baseline": ("baseline_start", "baseline_end"),
              "actual": ("actual_start", "actual_end")}[layer]
    start, end = (getattr(event, field) for field in fields)
    return (datetime.fromisoformat(start), datetime.fromisoformat(end)) if start and end else None


def split_blocks(events, days, layer, metadata):
    timed, all_day = {day: [] for day in days}, {day: [] for day in days}
    for event in events:
        interval = event_interval(event, layer)
        if interval is None:
            continue
        start, end = interval
        info = metadata.get(event.id, {})
        flag = (info.get("baseline_all_day") if layer == "baseline" else info.get("all_day")) if layer != "actual" else False
        for day in days:
            midnight = datetime.combine(day, time.min)
            next_day = midnight + timedelta(days=1)
            if start >= next_day or end <= midnight:
                continue
            if flag:
                all_day[day].append(event)
            else:
                begin = max(0, (start - midnight).total_seconds() / 60)
                finish = min(1440, (end - midnight).total_seconds() / 60)
                timed[day].append(Block(event, day, begin, finish))
    return {day: layout_overlaps(values) for day, values in timed.items()}, all_day


def color_for(event, status=None):
    status = event.status if status is None else status
    if status in STATUS_COLORS:
        return tuple(QColor(color) for color in STATUS_COLORS[status])
    palette = (("#7865D9", "#F1EEFF"), ("#508BD5", "#ECF4FF"), ("#C58C42", "#FFF6E8"),
               ("#B374B8", "#F9EEFA"), ("#489B9F", "#EAF7F7"))
    index = hashlib.blake2b(event.category.encode(), digest_size=1).digest()[0] % len(palette)
    return tuple(QColor(c) for c in palette[index])


def font(size, weight=QFont.Weight.Normal):
    f = QFont("Segoe UI")
    f.setPixelSize(size)
    f.setWeight(weight)
    return f


@dataclass(frozen=True)
class WrappedText:
    lines: tuple[str, ...]
    line_height: int
    truncated: bool


def fit_wrapped_text(value, face, width, height):
    """Fit complete lines, breaking long words and marking any omitted text."""
    metrics = QFontMetricsF(face)
    line_height = math.ceil(metrics.height())
    capacity = max(0, int(height // line_height))
    value = " ".join(value.split())
    if width <= 0 or not capacity or not value:
        return WrappedText((), line_height, bool(value))
    layout = QTextLayout(value, face)
    option = QTextOption()
    option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
    layout.setTextOption(option)
    # QTextLine offsets count UTF-16 units, including two units for emoji.
    encoded = value.encode("utf-16-le")
    lines, truncated = [], False
    layout.beginLayout()
    for row in range(capacity + 1):
        line = layout.createLine()
        if not line.isValid():
            break
        line.setLineWidth(width)
        if row == capacity:
            truncated = True
            break
        start, end = line.textStart(), line.textStart() + line.textLength()
        segment = encoded[start * 2:end * 2].decode("utf-16-le").rstrip()
        fitted = metrics.elidedText(segment, Qt.TextElideMode.ElideRight, width)
        truncated |= fitted != segment
        lines.append(fitted)
    layout.endLayout()
    if truncated and lines:
        lines[-1] = metrics.elidedText(lines[-1] + "…", Qt.TextElideMode.ElideRight, width)
    return WrappedText(tuple(lines), line_height, truncated)


def text(painter, rect, value, size=12, color=TEXT, weight=QFont.Weight.Normal, wrap=False):
    painter.setFont(font(size, weight))
    painter.setPen(color)
    flags = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
    painter.save()
    painter.setClipRect(rect, Qt.ClipOperation.IntersectClip)
    used = 0
    if wrap:
        fitted = fit_wrapped_text(value, painter.font(), rect.width(), rect.height())
        for row, line in enumerate(fitted.lines):
            painter.drawText(QRectF(rect.x(), rect.y() + row * fitted.line_height,
                                    rect.width(), fitted.line_height), flags, line)
        used = len(fitted.lines) * fitted.line_height
    elif rect.width() > 0 and rect.height() >= math.ceil(painter.fontMetrics().height()):
        value = painter.fontMetrics().elidedText(value, Qt.TextElideMode.ElideRight, int(rect.width()))
        painter.drawText(rect, flags, value)
        used = rect.height()
    painter.restore()
    return used


class HitCanvas(QWidget):
    def __init__(self, board):
        super().__init__()
        self.board = board
        self.hits = []
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def hit(self, point):
        return next((event for rect, event in reversed(self.hits) if rect.contains(point)), None)

    def mouseMoveEvent(self, event):
        self.setCursor(Qt.CursorShape.PointingHandCursor if self.hit(event.position()) else Qt.CursorShape.ArrowCursor)

    def context_position(self, point):
        return point

    def context_day(self, point):
        return self.board.focus

    def contextMenuEvent(self, event):
        point = self.context_position(event.pos())
        hit = self.hit(point)
        if hit is None:
            event.ignore()
            return
        self.board.clicked_day = self.context_day(point)
        self.board.context_requested.emit(hit.id, event.globalPos())
        event.accept()

    def event(self, event):
        if event.type() == QEvent.Type.ToolTip:
            hit = self.hit(event.pos())
            if hit:
                interval = event_interval(hit, self.board.layer)
                times = f"{interval[0]:%d.%m %H:%M} — {interval[1]:%d.%m %H:%M}" if interval else ""
                detail = escape(f"{hit.title}\n{times}\n{hit.category} · {STATUSES[hit.status]}").replace("\n", "<br>")
                QToolTip.showText(event.globalPos(), "<p>" + detail + "</p>", self)
                return True
            QToolTip.hideText()
        return super().event(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.board.selected_id is not None:
            self.board.activated.emit(self.board.selected_id)
        else:
            super().keyPressEvent(event)

    def draw_chip(self, painter, rect, event, compact=False):
        painter.save()
        painter.setClipRect(rect, Qt.ClipOperation.IntersectClip)
        accent, fill = color_for(event)
        selected = event.id == self.board.selected_id
        painter.setPen(QPen(ACCENT if selected else fill, 1.5 if selected else 1))
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, 7, 7)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(accent)
        stripe_margin = min(6, rect.height() / 4)
        painter.drawRoundedRect(QRectF(rect.x() + 1, rect.y() + stripe_margin, 3,
                                      rect.height() - stripe_margin * 2), 1.5, 1.5)
        left = min(10, max(3, rect.width() / 5))
        right = min(7, max(2, rect.width() / 7))
        content = rect.adjusted(left, 3, -right, -3)
        interval = event_interval(event, self.board.layer)
        if compact:
            title = event.title
            if self.board.mode == "month" and not self.board.is_all_day(event):
                title = f"{interval[0]:%H:%M} {title}" if interval else title
            text(painter, content, title, 11, accent, QFont.Weight.DemiBold)
        else:
            title_height = math.ceil(QFontMetricsF(font(12, QFont.Weight.DemiBold)).height())
            meta_metrics = QFontMetricsF(font(10))
            meta_height = math.ceil(meta_metrics.height())
            title_rect = QRectF(content)
            # Keep at least one complete title line; metadata uses only spare room.
            if interval and content.height() >= meta_height + 3 + title_height:
                full_time = f"{interval[0]:%H:%M} – {interval[1]:%H:%M}"
                time_label = full_time if meta_metrics.horizontalAdvance(full_time) <= content.width() else f"{interval[0]:%H:%M}"
                if meta_metrics.horizontalAdvance(time_label) <= content.width():
                    text(painter, QRectF(content.x(), content.y(), content.width(), meta_height), time_label, 10, accent)
                    title_rect.setTop(content.y() + meta_height + 3)
            used = text(painter, title_rect, event.title, 12, accent.darker(125), QFont.Weight.DemiBold, wrap=True)
            status_top = title_rect.y() + used + 4
            if used and content.bottom() - status_top >= meta_height:
                text(painter, QRectF(content.x(), status_top, content.width(), meta_height), STATUSES[event.status], 10, accent)
        painter.restore()
        self.hits.append((rect, event))


class TimeGrid(HitCanvas):
    def __init__(self, board):
        super().__init__(board)
        self.setMinimumHeight(self.board.hour_height * 24 + 1)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("white"))
        self.hits = []
        days = self.board.days
        width = (self.width() - GUTTER) / len(days)
        for col, day in enumerate(days):
            x = GUTTER + col * width
            if day == self.board.today():
                p.fillRect(QRectF(x, 0, width, self.height()), QColor("#FDFBFF"))
            elif day.weekday() >= 5:
                p.fillRect(QRectF(x, 0, width, self.height()), QColor("#FDFDFE"))
            p.setPen(QPen(GRID, 1))
            p.drawLine(QPoint(int(x), 0), QPoint(int(x), self.height()))
        for hour in range(24):
            y = hour * self.board.hour_height
            p.setPen(QPen(GRID, 1))
            p.drawLine(QPoint(GUTTER, y), QPoint(self.width(), y))
            p.setPen(QPen(QColor("#F7F7FB"), 1, Qt.PenStyle.DashLine))
            p.drawLine(QPoint(GUTTER, y + self.board.hour_height // 2), QPoint(self.width(), y + self.board.hour_height // 2))
            if hour:
                text(p, QRectF(3, y - 8, GUTTER - 10, 16), f"{hour:02}:00", 10, MUTED)
        for col, day in enumerate(days):
            for block in self.board.timed.get(day, []):
                lane_width = (width - 10) / block.lanes
                top = min(self.height() - 4, block.start / 60 * self.board.hour_height + 2)
                height = min(self.height() - top - 1, max(23, (block.end - block.start) / 60 * self.board.hour_height - 4))
                rect = QRectF(GUTTER + col * width + 5 + block.lane * lane_width,
                              top, max(9, lane_width - 3), max(1, height))
                self.draw_chip(p, rect, block.event)
        now = self.board.now()
        if now.date() in days:
            col = days.index(now.date())
            y = (now.hour + now.minute / 60) * self.board.hour_height
            x = GUTTER + col * width
            p.setPen(QPen(QColor("#E47786"), 1.4))
            p.drawLine(QPoint(int(x), int(y)), QPoint(int(x + width), int(y)))
            p.setBrush(QColor("#E47786"))
            p.drawEllipse(QRectF(x - 3, y - 3, 6, 6))
        p.end()

    def slot(self, point):
        col_width = (self.width() - GUTTER) / len(self.board.days)
        col = max(0, min(len(self.board.days) - 1, int((point.x() - GUTTER) / col_width)))
        minute = min(1410, max(0, int(point.y() / self.board.hour_height * 60) // 30 * 30))
        return self.board.days[col], minute

    def context_day(self, point):
        return self.slot(point)[0]

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            hit = self.hit(event.position())
            if hit:
                self.board.clicked_day = self.slot(event.position())[0]
                self.board.selected.emit(hit.id)
            else:
                day, _ = self.slot(event.position())
                self.board.date_selected.emit(day)

    def mouseDoubleClickEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        hit = self.hit(event.position())
        if hit:
            self.board.activated.emit(hit.id)


class DayHeader(HitCanvas):
    def context_position(self, point):
        return point + QPoint(self.board.scroll.horizontalScrollBar().value(), 0)

    def context_day(self, point):
        width = (self.board.grid.width() - GUTTER) / len(self.board.days)
        col = max(0, min(len(self.board.days) - 1, int((point.x() - GUTTER) / width)))
        return self.board.days[col]

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("white"))
        p.translate(-self.board.scroll.horizontalScrollBar().value(), 0)
        self.hits = []
        width = (self.board.grid.width() - GUTTER) / len(self.board.days)
        for col, day in enumerate(self.board.days):
            x = GUTTER + col * width
            text(p, QRectF(x + 12, 7, width - 16, 17), WEEKDAYS[day.weekday()], 10, MUTED, QFont.Weight.DemiBold)
            if day == self.board.today():
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(ACCENT)
                p.drawEllipse(QRectF(x + 9, 27, 27, 27))
                p.setFont(font(16, QFont.Weight.DemiBold))
                p.setPen(QColor("white"))
                p.drawText(QRectF(x + 9, 27, 27, 27), Qt.AlignmentFlag.AlignCenter, str(day.day))
            else:
                text(p, QRectF(x + 12, 28, width - 20, 25), str(day.day), 17, TEXT, QFont.Weight.DemiBold)
            for row, item in enumerate(self.board.all_day.get(day, [])[:2]):
                self.draw_chip(p, QRectF(x + 5, 63 + row * 25, width - 10, 22), item, compact=True)
            if len(self.board.all_day.get(day, [])) > 2:
                text(p, QRectF(x + 9, 113, width - 12, 18), f"Ещё {len(self.board.all_day[day]) - 2} · список", 10, MUTED)
        p.setPen(QPen(GRID, 1))
        p.drawLine(QPoint(0, self.height() - 1), QPoint(self.board.grid.width(), self.height() - 1))
        if any(self.board.all_day.values()):
            text(p, QRectF(2, 65, GUTTER - 5, 20), "Весь день", 9, MUTED)
        p.end()

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        point = event.position() + QPoint(self.board.scroll.horizontalScrollBar().value(), 0)
        hit = self.hit(point)
        if hit:
            width = (self.board.grid.width() - GUTTER) / len(self.board.days)
            self.board.clicked_day = self.board.days[min(len(self.board.days) - 1, int((point.x() - GUTTER) / width))]
            self.board.selected.emit(hit.id)
        elif point.x() >= GUTTER:
            width = (self.board.grid.width() - GUTTER) / len(self.board.days)
            col = min(len(self.board.days) - 1, int((point.x() - GUTTER) / width))
            self.board.date_selected.emit(self.board.days[col])
            if point.y() > 110:
                self.board.agenda_requested.emit()

    def mouseDoubleClickEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        point = event.position() + QPoint(self.board.scroll.horizontalScrollBar().value(), 0)
        hit = self.hit(point)
        if hit:
            self.board.activated.emit(hit.id)


class MonthGrid(HitCanvas):
    def context_day(self, point):
        return period_days(self.board.focus, "month")[self.cell(point)]

    def cell(self, point):
        col = max(0, min(6, int(point.x() / (self.width() / 7))))
        row = max(0, min(5, int((point.y() - 28) / ((self.height() - 28) / 6))))
        return row * 7 + col

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("white"))
        self.hits, self.more = [], []
        width, height = self.width() / 7, (self.height() - 28) / 6
        days = period_days(self.board.focus, "month")
        for col in range(7):
            text(p, QRectF(col * width + 12, 0, width - 16, 25), WEEKDAYS[col], 10, MUTED, QFont.Weight.DemiBold)
        for index, day in enumerate(days):
            x, y = index % 7 * width, 28 + index // 7 * height
            if day == self.board.focus:
                p.fillRect(QRectF(x, y, width, height), QColor("#FAF8FF"))
            elif day.month != self.board.focus.month:
                p.fillRect(QRectF(x, y, width, height), QColor("#FBFBFE"))
            p.setPen(QPen(GRID, 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(QRectF(x, y, width, height))
            if day == self.board.today():
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(ACCENT)
                p.drawEllipse(QRectF(x + 7, y + 5, 24, 24))
                p.setPen(QColor("white"))
                p.setFont(font(12, QFont.Weight.DemiBold))
                p.drawText(QRectF(x + 7, y + 5, 24, 24), Qt.AlignmentFlag.AlignCenter, str(day.day))
            else:
                text(p, QRectF(x + 12, y + 5, width - 16, 24), str(day.day), 12,
                     MUTED if day.month != self.board.focus.month else TEXT, QFont.Weight.DemiBold)
            items = list(self.board.all_day.get(day, [])) + [b.event for b in self.board.timed.get(day, [])]
            if height < 58:
                if items:
                    rect = QRectF(x + 34, y + 7, width - 38, 20)
                    text(p, rect, f"+{len(items)}", 10, MUTED)
                    self.more.append((rect, day))
                continue
            capacity = max(1, int((height - 36) / 23))
            shown = capacity if len(items) <= capacity else max(0, capacity - 1)
            for row, item in enumerate(items[:shown]):
                rect = QRectF(x + 5, y + 34 + row * 23, width - 10, 20)
                self.draw_chip(p, rect, item, compact=True)
            if len(items) > shown:
                rect = QRectF(x + 10, y + 34 + shown * 23, width - 16, 20)
                text(p, rect, f"+{len(items) - shown} событий", 10, MUTED)
                self.more.append((rect, day))
        p.end()

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or event.position().y() < 28:
            return
        hit = self.hit(event.position())
        if hit:
            self.board.clicked_day = period_days(self.board.focus, "month")[self.cell(event.position())]
            self.board.selected.emit(hit.id)
            return
        day = period_days(self.board.focus, "month")[self.cell(event.position())]
        if any(rect.contains(event.position()) for rect, _ in getattr(self, "more", [])):
            self.board.date_selected.emit(day)
            self.board.agenda_requested.emit()
        else:
            self.board.date_selected.emit(day)

    def mouseDoubleClickEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or event.position().y() < 28:
            return
        hit = self.hit(event.position())
        if hit:
            self.board.activated.emit(hit.id)


class CalendarBoard(QWidget):
    selected = Signal(int)
    activated = Signal(int)
    context_requested = Signal(int, QPoint)
    date_selected = Signal(object)
    agenda_requested = Signal()

    def __init__(self):
        super().__init__()
        self.focus = date.today()
        self.mode, self.layer, self.zone = "week", "current", "Europe/Moscow"
        self.selected_id = None
        self.clicked_day = None
        self.hour_height = HOUR
        self.days = period_days(self.focus, self.mode)
        self.timed, self.all_day = {}, {}
        self.metadata = {}
        self.stack = QStackedWidget()
        timeline = QWidget()
        layout = QVBoxLayout(timeline)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.header = DayHeader(self)
        self.header.setFixedHeight(61)
        layout.addWidget(self.header)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.grid = TimeGrid(self)
        self.scroll.setWidget(self.grid)
        self.scroll.horizontalScrollBar().valueChanged.connect(self.header.update)
        layout.addWidget(self.scroll)
        self.stack.addWidget(timeline)
        self.month = MonthGrid(self)
        self.month.setMinimumHeight(250)
        self.stack.addWidget(self.month)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.stack)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.grid.update)
        self.timer.start(60000)
        QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(7 * self.hour_height))

    def set_compact(self, compact):
        new_height = 52 if compact else HOUR
        if new_height == self.hour_height:
            return
        hour = self.scroll.verticalScrollBar().value() / self.hour_height
        self.hour_height = new_height
        self.grid.setMinimumHeight(new_height * 24 + 1)
        self.grid.update()
        QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(int(hour * new_height)))

    def now(self):
        return datetime.now(ZoneInfo(self.zone))

    def today(self):
        return self.now().date()

    def is_all_day(self, event):
        if self.layer == "actual":
            return False
        info = self.metadata.get(event.id, {})
        return bool(info.get("baseline_all_day" if self.layer == "baseline" else "all_day"))

    def set_data(self, focus, mode, layer, events, metadata, selected_id=None, zone="Europe/Moscow"):
        self.focus, self.mode, self.layer, self.zone, self.selected_id = focus, mode, layer, zone, selected_id
        self.metadata = metadata
        self.clicked_day = None
        self.days = period_days(focus, mode)
        self.timed, self.all_day = split_blocks(events, self.days, layer, metadata)
        self.stack.setCurrentIndex(1 if mode == "month" else 0)
        self.grid.setMinimumWidth(GUTTER + len(self.days) * 86 if mode != "month" else 0)
        rows = min(2, max((len(items) for items in self.all_day.values()), default=0))
        extra = any(len(items) > 2 for items in self.all_day.values())
        self.header.setFixedHeight(61 + rows * 25 + (22 if extra else 0))
        for canvas in (self.header, self.grid, self.month):
            canvas.hits = []
            canvas.update()
