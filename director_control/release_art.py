"""Illustration for the native update announcement, drawn at the screen's resolution."""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from .theme import color


class ReleaseArtwork(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(116, 96)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._phase = 'available'

    def set_phase(self, phase):
        if self._phase != phase:
            self._phase = phase
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setWindow(0, 0, 116, 96)
        rule = color('hover_border')
        ink = color('segment_selected')
        accent = color('primary')

        # Two leaves at different angles give the calendar depth.
        painter.save()
        painter.translate(58, 45)
        painter.rotate(11)
        painter.setPen(QPen(rule, 1.4))
        painter.setBrush(color('selection'))
        painter.drawRoundedRect(QRectF(-32, -29, 66, 64), 8, 8)
        painter.restore()

        painter.save()
        painter.translate(48, 43)
        painter.rotate(-10)
        painter.setPen(QPen(rule, 1.5))
        painter.setBrush(color('surface'))
        painter.drawRoundedRect(QRectF(-32, -27, 67, 65), 8, 8)
        painter.drawLine(-31, -9, 34, -9)
        pen = QPen(ink, 3.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        for x in (-17, 18):
            painter.drawLine(x, -31, x, -21)
        painter.setPen(Qt.PenStyle.NoPen)
        for row in range(2):
            for column in range(3):
                painter.setBrush(accent if (row, column) == (0, 1) else rule)
                painter.drawRoundedRect(QRectF(-22 + column * 16, -1 + row * 14, 11, 9), 2.5, 2.5)
        painter.restore()

        painter.translate(87, 70)
        painter.setPen(QPen(color('surface'), 2))
        painter.setBrush(accent)
        painter.drawEllipse(QPointF(), 16, 16)
        painter.setPen(QPen(Qt.GlobalColor.white, 2.4, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if self._phase == 'ready':
            painter.drawPolyline(QPolygonF([QPointF(-7, 0), QPointF(-2, 5), QPointF(7, -5)]))
        elif self._phase == 'error':
            painter.drawLine(0, -7, 0, 1)
            painter.drawPoint(0, 6)
        elif self._phase == 'downloading':
            painter.drawLine(0, -8, 0, 3)
            painter.drawPolyline(QPolygonF([QPointF(-5, -1), QPointF(0, 4), QPointF(5, -1)]))
            painter.drawLine(-6, 8, 6, 8)
        else:
            painter.drawLine(-5, 5, 5, -5)
            painter.drawPolyline(QPolygonF([QPointF(-4, -5), QPointF(5, -5), QPointF(5, 4)]))
