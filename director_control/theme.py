"""Shared desktop design tokens and small vector icons."""
from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

ACCENT = "#6956E8"
INK = "#202436"
MUTED = "#85889B"

STYLE = """
QWidget { color: #202436; font-family: 'Segoe UI', 'Inter', sans-serif; font-size: 12px; }
QMainWindow { background: #F7F8FC; }
QDialog, QWidget#DialogContent { background: white; }
QWidget#FormContent { background: #F7F8FC; }
QWidget#Workspace, QWidget#CalendarPage { background: #F7F8FC; }
QFrame#Sidebar { background: #FFFFFF; border-right: 1px solid #ECECF4; }
QFrame#Sidebar QCheckBox { background: transparent; }
QLabel { background: transparent; border: none; }
QLabel#Brand { font-size: 16px; font-weight: 750; letter-spacing: 1px; }
QLabel#BrandSub, QLabel#Eyebrow { color: #9698AA; font-size: 10px; font-weight: 650; letter-spacing: 1px; }
QLabel#Logo { background: #6956E8; color: white; border-radius: 12px; font-size: 21px; font-weight: 700; }
QLabel#PageTitle { font-size: 26px; font-weight: 700; letter-spacing: -0.5px; }
QLabel#PeriodTitle { font-size: 20px; font-weight: 700; }
QLabel#Muted { color: #85889B; }
QLabel#SectionTitle { font-size: 15px; font-weight: 650; }
QLabel#EventTitle { font-size: 19px; font-weight: 700; }
QLabel#StatusPill { color: #6956E8; background: #F0EDFF; border-radius: 7px; padding: 6px 9px; }
QFrame#Surface, QFrame#Inspector { background: white; border: 1px solid #ECECF4; border-radius: 14px; }
QFrame#Metric { background: white; border: 1px solid #ECECF4; border-radius: 11px; }
QLabel#CardTitle { color: #85889B; font-size: 11px; }
QLabel#CardValue { color: #272C44; font-size: 22px; font-weight: 700; }
QPushButton { background: white; border: 1px solid #E3E4EF; border-radius: 8px; padding: 9px 13px; font-weight: 600; }
QPushButton:hover { background: #F6F4FF; border-color: #CCC5FA; }
QPushButton:pressed { background: #EBE6FF; }
QPushButton:disabled { color: #B3B5C4; border-color: #EEEFF5; background: #FAFAFD; }
QPushButton#Primary { background: #6956E8; border-color: #6956E8; color: white; }
QPushButton#Primary:hover { background: #5B49D6; }
QPushButton#Primary:disabled { background: #C5BDF4; border-color: #C5BDF4; }
QPushButton#Nav { background: transparent; border: none; text-align: left; color: #75798E; padding: 12px 15px; }
QPushButton#Nav:hover { background: #F6F5FC; }
QPushButton#Nav:checked { color: #6956E8; background: #F0EDFF; font-weight: 700; }
QPushButton#Segment { border: none; background: transparent; padding: 7px 12px; color: #86899C; }
QPushButton#Segment:checked { background: white; color: #5140BF; border: 1px solid #E5E1F7; }
QFrame#Segments { background: #EFEEF6; border-radius: 9px; }
QPushButton#Arrow { padding: 4px; font-size: 20px; min-width: 28px; }
QPushButton#Danger { color: #C45C70; }
QPushButton#Link { color: #6956E8; background: transparent; border: none; text-align: left; padding-left: 0; }
QTabWidget::pane { border: none; background: transparent; }
QLineEdit, QComboBox, QDateTimeEdit, QDateEdit, QSpinBox { background: white; border: 1px solid #E3E4EF;
    border-radius: 8px; padding: 7px 10px; min-height: 22px; selection-background-color: #DDD6FF; }
QLineEdit:focus, QComboBox:focus, QDateTimeEdit:focus, QDateEdit:focus, QSpinBox:focus { border: 1px solid #9C8DF3; }
QLineEdit:disabled, QDateTimeEdit:disabled { background: #F4F5F9; color: #8A8DA0; }
QLineEdit#Search { background: #FFFFFF; padding-left: 12px; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: white; border: 1px solid #E3E4EF; selection-background-color: #F0EDFF; }
QGroupBox { background: white; border: 1px solid #ECECF4; border-radius: 12px; margin-top: 17px; padding: 22px 16px 16px; font-weight: 650; }
QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 5px; }
QTableWidget { background: white; alternate-background-color: #FCFCFF; border: 1px solid #ECECF4; border-radius: 10px;
    gridline-color: #F0F0F6; selection-background-color: #F0EDFF; selection-color: #403280; outline: none; }
QTableWidget::item { padding: 7px; border-bottom: 1px solid #F0F0F6; }
QHeaderView::section { background: #F9F9FD; color: #878B9F; border: none; border-bottom: 1px solid #ECECF4; padding: 12px 8px; font-size: 11px; font-weight: 600; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: transparent; width: 7px; margin: 2px; }
QScrollBar::handle:vertical { background: #DADBE7; border-radius: 3px; min-height: 30px; }
QScrollBar:horizontal { background: transparent; height: 7px; }
QScrollBar::handle:horizontal { background: #DADBE7; border-radius: 3px; min-width: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QCheckBox { spacing: 9px; font-weight: 400; }
QCheckBox::indicator { width: 15px; height: 15px; }
QToolTip { background: #26243B; color: #FFFFFF; border: none; padding: 8px; font-size: 12px; }
QMenu#EventContextMenu { background: white; border: 1px solid #E3E4EF; border-radius: 9px; padding: 6px; }
QMenu#EventContextMenu::item { padding: 9px 20px 9px 28px; border-radius: 6px; }
QMenu#EventContextMenu::item:disabled { color: #85889B; }
QMenu#EventContextMenu::separator { height: 1px; background: #ECECF4; margin: 4px 10px; }
QCalendarWidget { background: white; }
QCalendarWidget QWidget { alternate-background-color: white; }
QCalendarWidget QToolButton { color: #55596E; background: white; border: none; font-size: 11px; padding: 3px; }
QCalendarWidget QMenu { background: white; }
QCalendarWidget QAbstractItemView { background: white; color: #61667C; font-size: 11px; selection-background-color: #6956E8; selection-color: white; outline: none; }
QWidget#MiniCalendar, QWidget#MiniCalendarHeader { background: white; }
QToolButton#MiniArrow { background: transparent; border: 1px solid transparent; border-radius: 7px; padding: 0; }
QToolButton#MiniArrow:hover, QToolButton#MiniArrow:focus { background: #F0EDFF; border-color: #E4DEFC; }
QToolButton#MiniArrow:pressed { background: #E5DFFF; }
QToolButton#MiniMonth { color: #454B63; background: transparent; border: none; border-radius: 7px;
    font-size: 11px; font-weight: 650; padding: 5px 2px; }
QToolButton#MiniMonth:hover, QToolButton#MiniMonth:focus { color: #6956E8; background: #F3F0FF; }
QCalendarWidget#MiniDateGrid QAbstractItemView { background: white; alternate-background-color: white;
    color: #969AAF; border: none; outline: none; font-size: 10px; selection-background-color: transparent; }
QMenu#MiniCalendarMenu { background: white; border: 1px solid #E3E4EF; border-radius: 9px; padding: 6px; }
QMenu#MiniCalendarMenu::item { padding: 7px 20px 7px 25px; border-radius: 5px; }
QMenu#MiniCalendarMenu::item:selected { background: #F0EDFF; color: #5140BF; }
QMenu#MiniCalendarMenu::separator { height: 1px; background: #ECECF4; margin: 4px 8px; }
QProgressBar { background: #EEEAFB; border: none; border-radius: 3px; height: 5px; text-align: center; }
QProgressBar::chunk { background: #6956E8; border-radius: 3px; }
"""

_PATHS = {
    "calendar": '<rect x="3" y="5" width="18" height="16" rx="3"/><path d="M7 3v4m10-4v4M3 10h18M7 14h2m4 0h2m-8 4h2"/>',
    "chart": '<path d="M4 3v17h17M8 16v-5m5 5V7m5 9v-8"/>',
    "history": '<path d="M3 11a9 9 0 1 1 2 7M3 5v6h6m3-4v6l4 2"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="m9 3-1 3-3 1-2 4 2 2v4l4 2 3-1 3 1 4-2v-4l2-2-2-4-3-1-1-3z"/>',
    "sync": '<path d="M20 8a8 8 0 0 0-14-3L3 8m0-5v5h5m-4 8a8 8 0 0 0 14 3l3-3m0 5v-5h-5"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "check": '<path d="m5 12 4 4L19 6"/>',
    "chevron_left": '<path d="m14 6-6 6 6 6"/>',
    "chevron_right": '<path d="m10 6 6 6-6 6"/>',
}


def icon(name, color=ACCENT):
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><g fill="none" stroke="{color}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{_PATHS[name]}</g></svg>'
    pixmap = QPixmap(48, 48)
    pixmap.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)
