"""Compact date picker with a custom header and softly highlighted day cells."""
from PySide6.QtCore import QDate, QEvent, QLocale, QPoint, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QTextCharFormat
from PySide6.QtWidgets import (
    QAbstractItemView, QCalendarWidget, QDialog, QHBoxLayout, QInputDialog,
    QMenu, QToolButton, QVBoxLayout, QWidget,
)

from .theme import icon


class MiniDateGrid(QCalendarWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MiniDateGrid")
        self._cell_rects = {}
        self._hovered = None
        self.setLocale(QLocale(QLocale.Language.Russian))
        self.setNavigationBarVisible(False)
        self.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        self.setHorizontalHeaderFormat(QCalendarWidget.HorizontalHeaderFormat.ShortDayNames)
        self.setFirstDayOfWeek(Qt.DayOfWeek.Monday)
        self.setGridVisible(False)
        header = QTextCharFormat()
        header.setForeground(QColor("#969AAF"))
        for day in Qt.DayOfWeek:
            self.setWeekdayTextFormat(day, header)
        self._view = self.findChild(QAbstractItemView)
        self._view.setMouseTracking(True)
        self._view.viewport().setMouseTracking(True)
        self._view.viewport().installEventFilter(self)
        self.currentPageChanged.connect(self._page_changed)

    def _page_changed(self, year, month):
        self._cell_rects.clear()
        self._hovered = None
        self._view.viewport().unsetCursor()

    def eventFilter(self, watched, event):
        view = getattr(self, "_view", None)
        if view is not None and watched is view.viewport():
            if event.type() == QEvent.Type.MouseMove:
                day = next((day for day, rect in self._cell_rects.items()
                            if rect.contains(event.position().toPoint())
                            and self.minimumDate() <= day <= self.maximumDate()), None)
                self._set_hovered(day)
                watched.setCursor(Qt.CursorShape.PointingHandCursor if day else Qt.CursorShape.ArrowCursor)
            elif event.type() == QEvent.Type.Leave:
                self._set_hovered(None)
                watched.unsetCursor()
        return super().eventFilter(watched, event)

    def _set_hovered(self, day):
        if day == self._hovered:
            return
        previous, self._hovered = self._hovered, day
        if previous is not None:
            self.updateCell(previous)
        if day is not None:
            self.updateCell(day)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._cell_rects.clear()
        self._hovered = None

    def paintCell(self, painter, rect, day):
        self._cell_rects[QDate(day)] = QRect(rect)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(rect, QColor("white"))
        selected = day == self.selectedDate()
        today = day == QDate.currentDate()
        current = day.month() == self.monthShown() and day.year() == self.yearShown()
        enabled = self.minimumDate() <= day <= self.maximumDate()
        size = max(0, min(23, rect.width() - 2, rect.height() - 2))
        circle = QRectF(rect.center().x() - size / 2, rect.center().y() - size / 2, size, size)
        painter.setPen(Qt.PenStyle.NoPen)
        if selected:
            painter.setBrush(QColor("#6956E8"))
            painter.drawEllipse(circle)
        elif day == self._hovered and enabled:
            painter.setBrush(QColor("#F0EDFF"))
            painter.drawEllipse(circle)
        if today and not selected:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor("#C4BAF8"), 1))
            painter.drawEllipse(circle)
        color = ("#FFFFFF" if selected else "#D6D9E4" if not enabled else "#B9BDCB" if not current
                 else "#6956E8" if today or day == self._hovered else "#9C7F91" if day.dayOfWeek() >= 6 else "#535B72")
        face = QFont(self.font())
        face.setPixelSize(11)
        face.setWeight(QFont.Weight.DemiBold if selected or today else QFont.Weight.Normal)
        painter.setFont(face)
        painter.setPen(QColor(color))
        painter.drawText(circle, Qt.AlignmentFlag.AlignCenter, str(day.day()))
        painter.restore()


class MiniCalendar(QWidget):
    clicked = Signal(QDate)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MiniCalendar")
        self.setLocale(QLocale(QLocale.Language.Russian))
        self.setMinimumWidth(165)
        self.setFixedHeight(216)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)
        header = QWidget()
        header.setObjectName("MiniCalendarHeader")
        header.setFixedHeight(29)
        row = QHBoxLayout(header)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)
        self.previous = self._arrow("chevron_left", "Предыдущий месяц")
        self.next = self._arrow("chevron_right", "Следующий месяц")
        self.month_button = QToolButton()
        self.month_button.setObjectName("MiniMonth")
        self.month_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.month_button.setToolTip("Выбрать месяц или год")
        self.month_button.setAccessibleName("Выбор месяца и года")
        row.addWidget(self.previous)
        row.addWidget(self.month_button, 1)
        row.addWidget(self.next)
        layout.addWidget(header)
        self.grid = MiniDateGrid(self)
        layout.addWidget(self.grid, 1)
        self.previous.clicked.connect(self.grid.showPreviousMonth)
        self.next.clicked.connect(self.grid.showNextMonth)
        self.month_button.clicked.connect(self._show_month_menu)
        self.grid.currentPageChanged.connect(self._update_header)
        self.grid.clicked.connect(self.clicked.emit)
        self.grid.activated.connect(self.clicked.emit)
        self._update_header(self.grid.yearShown(), self.grid.monthShown())

    def _arrow(self, name, label):
        button = QToolButton()
        button.setObjectName("MiniArrow")
        button.setFixedSize(25, 27)
        button.setIcon(icon(name, "#7A7893"))
        button.setIconSize(QSize(14, 14))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setToolTip(label)
        button.setAccessibleName(label)
        return button

    def _update_header(self, year, month):
        name = self.locale().standaloneMonthName(month, QLocale.FormatType.LongFormat).capitalize()
        self.month_button.setText(f"{name} {year}")
        first = QDate(year, month, 1)
        self.previous.setEnabled(first > QDate(self.grid.minimumDate().year(), self.grid.minimumDate().month(), 1))
        self.next.setEnabled(first < QDate(self.grid.maximumDate().year(), self.grid.maximumDate().month(), 1))

    def setSelectedDate(self, day):
        self.grid.setSelectedDate(day)

    def _show_month_menu(self):
        menu = QMenu(self)
        menu.setObjectName("MiniCalendarMenu")
        menu.setCursor(Qt.CursorShape.PointingHandCursor)
        for month in range(1, 13):
            action = menu.addAction(self.locale().standaloneMonthName(month, QLocale.FormatType.LongFormat).capitalize())
            action.setData(month)
            action.setCheckable(True)
            action.setChecked(month == self.grid.monthShown())
            action.triggered.connect(lambda checked, month=month: self.grid.setCurrentPage(self.grid.yearShown(), month))
        menu.addSeparator()
        menu.addAction("Выбрать год…", self._choose_year)
        try:
            menu.exec(self.month_button.mapToGlobal(QPoint(0, self.month_button.height() + 4)))
        finally:
            menu.deleteLater()

    def _choose_year(self):
        dialog = QInputDialog(self.window())
        dialog.setWindowTitle("Год календаря")
        dialog.setLabelText("Выбери год")
        dialog.setInputMode(QInputDialog.InputMode.IntInput)
        dialog.setIntRange(max(1, self.grid.minimumDate().year()), self.grid.maximumDate().year())
        dialog.setIntValue(self.grid.yearShown())
        dialog.setOkButtonText("Выбрать")
        dialog.setCancelButtonText("Отмена")
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.grid.setCurrentPage(dialog.intValue(), self.grid.monthShown())
        dialog.deleteLater()
