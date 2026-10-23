"""Status-colored menu rows with native QMenu interaction and keyboard support."""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import QMenu

from .calendar_view import color_for, event_foreground, event_hover
from .theme import color as theme_color
from .storage import STATUSES


class EventStatusMenu(QMenu):
    def __init__(self, event, parent=None):
        super().__init__(parent)
        self._calendar_event = event
        self.setObjectName("EventContextMenu")

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(self.font())
        for action in self.actions():
            if action.data() not in STATUSES or not action.isVisible():
                continue
            bounds = QRectF(self.actionGeometry(action))
            accent, fill = color_for(self._calendar_event, status=action.data())
            active = action == self.activeAction()
            # Cover the native selection so hover retains the status color too.
            painter.fillRect(bounds, theme_color("surface"))
            painter.setPen(QPen(accent, 1) if active else QPen(Qt.PenStyle.NoPen))
            painter.setBrush(event_hover(fill) if active else fill)
            painter.drawRoundedRect(bounds.adjusted(3, 1, -3, -1), 6, 6)
            painter.setPen(event_foreground(accent))
            painter.drawText(bounds.adjusted(40, 0, -16, 0),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, action.text())
            if action.isChecked():
                painter.setPen(QPen(accent, 2, Qt.PenStyle.SolidLine,
                                    Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                x, y = bounds.left() + 16, bounds.center().y()
                painter.drawLine(int(x), int(y), int(x + 3), int(y + 3))
                painter.drawLine(int(x + 3), int(y + 3), int(x + 9), int(y - 4))
        painter.end()
