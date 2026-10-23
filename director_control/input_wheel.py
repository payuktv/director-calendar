"""Keep mouse-wheel scrolling from editing form values throughout the application."""
from PySide6.QtCore import QEvent, QObject, QPointF
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import (
    QApplication, QAbstractScrollArea, QAbstractSpinBox, QComboBox, QDial,
    QLineEdit, QSlider, QWidget,
)


def install_input_wheel_guard(app):
    if not hasattr(app, "_input_wheel_guard"):
        app._input_wheel_guard = InputWheelGuard(app)
        app.installEventFilter(app._input_wheel_guard)


class InputWheelGuard(QObject):
    def eventFilter(self, watched, event):
        if event.type() != QEvent.Type.Wheel or not isinstance(watched, QWidget):
            return False
        field = watched
        while field is not None:
            if isinstance(field, (QAbstractSpinBox, QComboBox, QLineEdit, QSlider, QDial)):
                self._scroll_parent(field, event)
                event.accept()
                return True
            # Popup calendars and open lists scroll within their own window.
            if field.isWindow():
                break
            field = field.parentWidget()
        return False

    @staticmethod
    def _scroll_parent(field, event):
        parent = field.parentWidget()
        while parent is not None:
            if isinstance(parent, QAbstractScrollArea):
                viewport = parent.viewport()
                forwarded = QWheelEvent(
                    QPointF(viewport.mapFromGlobal(event.globalPosition().toPoint())), event.globalPosition(),
                    event.pixelDelta(), event.angleDelta(), event.buttons(), event.modifiers(),
                    event.phase(), event.inverted(), device=event.pointingDevice(),
                )
                forwarded.ignore()
                QApplication.sendEvent(viewport, forwarded)
                if forwarded.isAccepted():
                    return
            if parent.isWindow():
                break
            parent = parent.parentWidget()
