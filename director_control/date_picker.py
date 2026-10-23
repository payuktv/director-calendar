"""Shared date-field interaction and a padded, softly shadowed native popup."""
from weakref import ref

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QRect, QTimer, Qt, Slot
from PySide6.QtGui import QColor, QMouseEvent
from PySide6.QtWidgets import QApplication, QDateEdit, QGraphicsDropShadowEffect, QStyle, QStyleOptionComboBox, QWidget
from shiboken6 import isValid

from .mini_calendar import MiniCalendar


def install_date_picker(control):
    control.setCalendarPopup(True)
    control.setCalendarWidget(MiniCalendar(control))
    control._date_picker = DatePicker(control)


class DatePicker(QObject):
    GAP = 8

    def __init__(self, control):
        super().__init__(control)
        self._control = ref(control)
        self._outside_cursor = False
        self.calendar = control.calendarWidget()
        self.popup = self.calendar.window()
        self.popup.setObjectName("DatePickerPopup")
        self.popup.setWindowFlags(self.popup.windowFlags() | Qt.WindowType.FramelessWindowHint
                                  | Qt.WindowType.NoDropShadowWindowHint)
        self.popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.popup.setAttribute(Qt.WidgetAttribute.WA_NoMouseReplay)
        self.popup.setCursor(Qt.CursorShape.ArrowCursor)
        self.popup.layout().setContentsMargins(16, 12, 16, 20)
        self.calendar.setProperty("datePopup", True)
        self.calendar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.calendar.style().unpolish(self.calendar)
        self.calendar.style().polish(self.calendar)
        self.calendar.setMinimumSize(224, 236)
        self.calendar.layout().setContentsMargins(10, 8, 10, 8)
        shadow = QGraphicsDropShadowEffect(self.calendar)
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(32, 36, 54, 35))
        self.calendar.setGraphicsEffect(shadow)
        self.control.installEventFilter(self)
        self.control.lineEdit().installEventFilter(self)
        self.popup.installEventFilter(self)
        self.control.destroyed.connect(self._restore_cursor)

    @property
    def control(self):
        return self._control()

    def _date_clicked(self, event):
        if isinstance(self.control, QDateEdit):
            return True
        # The event form uses dd.MM.yyyy HH:mm; keep its time portion editable by mouse.
        edit = self.control.lineEdit()
        point = edit.mapFromGlobal(event.globalPosition().toPoint())
        return not edit.rect().contains(point) or edit.cursorPositionAt(point) <= 10

    def eventFilter(self, watched, event):
        popup = getattr(self, "popup", None)
        if popup is None or not isValid(popup) or self.control is None or not isValid(self.control):
            return False
        kind = event.type()
        if kind in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick):
            if event.button() == Qt.MouseButton.LeftButton and self.control.isEnabled() and not self.control.isReadOnly():
                field = QRect(self.control.mapToGlobal(QPoint()), self.control.size())
                field_clicked = watched in (self.control, self.control.lineEdit()) or (
                    self.popup.isVisible() and QApplication.activePopupWidget() in (None, self.popup)
                    and field.contains(event.globalPosition().toPoint()))
                if field_clicked and self._date_clicked(event):
                    # A popup grab may deliver this input click to its QWindow first.
                    # Consume it before Qt can dismiss the popup and replay the click.
                    if self.popup.isVisible():
                        self.popup.hide()
                    else:
                        self.control.setFocus(Qt.FocusReason.MouseFocusReason)
                        self._open()
                    return True
        if watched is self.popup:
            if kind == QEvent.Type.Show:
                QApplication.instance().installEventFilter(self)
                QTimer.singleShot(0, self._position)
            elif kind == QEvent.Type.Hide:
                QApplication.instance().removeEventFilter(self)
                self._restore_cursor()
                self._clear_hover()
        if kind == QEvent.Type.MouseMove and self.popup.isVisible():
            bounds = QRect(self.calendar.mapToGlobal(QPoint()), self.calendar.size())
            if not bounds.contains(event.globalPosition().toPoint()):
                self._clear_hover()
                if not self._outside_cursor:
                    QApplication.setOverrideCursor(Qt.CursorShape.ArrowCursor)
                    self._outside_cursor = True
            else:
                self._restore_cursor()
        if kind == QEvent.Type.MouseButtonPress and self.popup.isVisible() and isinstance(watched, QWidget):
            if QApplication.activePopupWidget() in (None, self.popup):
                bounds = QRect(self.calendar.mapToGlobal(QPoint()), self.calendar.size())
                if not bounds.contains(event.globalPosition().toPoint()):
                    self.popup.hide()
                    return watched.window() is self.popup
        return False

    @Slot()
    def _restore_cursor(self):
        if getattr(self, "_outside_cursor", False):
            QApplication.restoreOverrideCursor()
            self._outside_cursor = False

    def _open(self):
        # Qt exposes no public popup opener; delegate to its arrow without filtering the click again.
        option = QStyleOptionComboBox()
        option.initFrom(self.control)
        arrow = self.control.style().subControlRect(
            QStyle.ComplexControl.CC_ComboBox, option, QStyle.SubControl.SC_ComboBoxArrow, self.control)
        point = arrow.center()
        for kind, buttons in ((QEvent.Type.MouseButtonPress, Qt.MouseButton.LeftButton),
                              (QEvent.Type.MouseButtonRelease, Qt.MouseButton.NoButton)):
            event = QMouseEvent(kind, QPointF(point), QPointF(self.control.mapToGlobal(point)),
                                Qt.MouseButton.LeftButton, buttons, Qt.KeyboardModifier.NoModifier)
            if kind == QEvent.Type.MouseButtonPress:
                self.control.mousePressEvent(event)
            else:
                self.control.mouseReleaseEvent(event)

    def _clear_hover(self):
        if isValid(self.calendar) and isValid(self.calendar._view):
            self.calendar._set_hovered(None)
            self.calendar._view.viewport().setCursor(Qt.CursorShape.ArrowCursor)

    @Slot()
    def _position(self):
        if not isValid(self.popup) or self.control is None or not isValid(self.control) or not self.popup.isVisible():
            return
        self.popup.layout().activate()
        field = QRect(self.control.mapToGlobal(QPoint()), self.control.size())
        screen = (QApplication.screenAt(field.center()) or self.control.screen()).availableGeometry()
        margins = self.popup.layout().contentsMargins()
        x = field.left() - margins.left()
        y = field.bottom() + 1 + self.GAP - margins.top()
        if y + self.popup.height() > screen.bottom() + 1:
            y = field.top() - self.GAP - self.popup.height() + margins.bottom()
        x = max(screen.left(), min(x, screen.right() + 1 - self.popup.width()))
        y = max(screen.top(), min(y, screen.bottom() + 1 - self.popup.height()))
        self.popup.move(x, y)
