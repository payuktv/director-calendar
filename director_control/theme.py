"""Shared desktop design tokens and small vector icons."""
from string import Template

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

# Shared tokens also drive custom-painted calendars, menus and charts.
LIGHT = {
    "frozen_day": "#EEE8F5",
    "text": "#202436", "background": "#F7F8FC", "surface": "#FFFFFF",
    "border": "#ECECF4", "control_border": "#E3E4EF", "muted": "#85889B",
    "subtle": "#9698AA", "accent": "#6956E8", "primary": "#6956E8",
    "primary_hover": "#5B49D6", "soft_accent": "#F0EDFF", "hover": "#F6F4FF",
    "hover_border": "#CCC5FA", "pressed": "#EBE6FF", "disabled_text": "#B3B5C4",
    "disabled_border": "#EEEFF5", "disabled_surface": "#FAFAFD", "primary_disabled": "#C5BDF4",
    "nav_text": "#75798E", "nav_hover": "#F6F5FC", "segment_text": "#86899C",
    "secondary_text": "#64697D",
    "release_tint": "#E5DFFC",
    "segment_selected": "#5140BF", "segment_border": "#E5E1F7", "segments": "#EFEEF6",
    "danger": "#C45C70", "selection": "#DDD6FF", "focus_border": "#9C8DF3",
    "readonly_surface": "#F4F5F9", "readonly_text": "#8A8DA0", "table_alternate": "#FCFCFF",
    "table_grid": "#F0F0F6", "selection_text": "#403280", "table_header": "#F9F9FD",
    "header_text": "#878B9F", "scrollbar": "#DADBE7", "tooltip": "#26243B",
    "popup_border": "#E8E5F3", "mini_hover_border": "#E4DEFC", "mini_pressed": "#E5DFFF",
    "mini_heading": "#454B63", "mini_heading_hover": "#F3F0FF", "mini_header": "#969AAF",
    "progress": "#EEEAFB", "card_value": "#272C44", "icon": "#8B89A3",
    "mini_icon": "#7A7893", "calendar_text": "#373C52", "calendar_muted": "#9296AB",
    "grid": "#EEF0F6", "half_grid": "#F7F7FB", "today": "#FDFBFF",
    "weekend": "#FDFDFE", "month_focus": "#FAF8FF", "outside_month": "#FBFBFE",
    "now": "#E47786", "mini_today": "#C4BAF8", "mini_disabled": "#D6D9E4",
    "mini_outside": "#B9BDCB", "mini_weekend": "#9C7F91", "mini_text": "#535B72",
    "plan_bar": "#B5A8F4", "actual_bar": "#57B89F", "plan_legend": "#A28DE8",
    "actual_legend": "#43A88D", "unplanned_bar": "#B58B46",
}
DARK = {
    **LIGHT,
    "frozen_day": "#453D55",
    "text": "#E4EAF5", "background": "#141923", "surface": "#1E2533",
    "border": "#30394B", "control_border": "#3B465C", "muted": "#A1ADC2",
    "subtle": "#94A0B6", "accent": "#B5A5FF", "primary": "#7662DE",
    "primary_hover": "#8672EE", "soft_accent": "#332D50", "hover": "#2C3348",
    "hover_border": "#736499", "pressed": "#3D355D", "disabled_text": "#78849A",
    "disabled_border": "#343D50", "disabled_surface": "#242B39", "primary_disabled": "#4D446D",
    "nav_text": "#B0BBD0", "nav_hover": "#262D40", "segment_text": "#A1ADC2",
    "secondary_text": "#B0BBD0",
    "release_tint": "#403452",
    "segment_selected": "#CEBFFF", "segment_border": "#554976", "segments": "#191F2C",
    "danger": "#F09AAC", "selection": "#524476", "focus_border": "#B5A5FF",
    "readonly_surface": "#252C3A", "readonly_text": "#95A1B7", "table_alternate": "#222A3A",
    "table_grid": "#2D3648", "selection_text": "#E3D9FF", "table_header": "#252D3F",
    "header_text": "#A5B1C7", "scrollbar": "#4D5870", "tooltip": "#39425B",
    "popup_border": "#4C4565", "mini_hover_border": "#554976", "mini_pressed": "#473B66",
    "mini_heading": "#D2DBEC", "mini_heading_hover": "#332D50", "mini_header": "#9AA8C1",
    "progress": "#332D50", "card_value": "#E4EAF5", "icon": "#B3AACF",
    "mini_icon": "#B8AFD3", "calendar_text": "#DCE4F3", "calendar_muted": "#9EACC4",
    "grid": "#30394B", "half_grid": "#283143", "today": "#26273D",
    "weekend": "#1B2230", "month_focus": "#2E2B46", "outside_month": "#1B212E",
    "now": "#F18CA1", "mini_today": "#9B8AE0", "mini_disabled": "#627088",
    "mini_outside": "#77859D", "mini_weekend": "#C2A4BC", "mini_text": "#CCD5E6",
    "plan_bar": "#B5A5FF", "actual_bar": "#6ED2B4", "plan_legend": "#B5A5FF",
    "actual_legend": "#6ED2B4", "unplanned_bar": "#D0AE72",
}

_STYLE_TEMPLATE = """
QWidget { color: $text; font-family: 'Segoe UI', 'Inter', sans-serif; font-size: 12px; }
QMainWindow { background: $background; }
QDialog, QWidget#DialogContent { background: $surface; }
QWidget#FormContent { background: $background; }
QWidget#Workspace, QWidget#CalendarPage { background: $background; }
QFrame#Sidebar { background: $surface; border-right: 1px solid $border; }
QFrame#Sidebar QCheckBox { background: transparent; }
QLabel { background: transparent; border: none; }
QLabel#Brand { font-size: 16px; font-weight: 750; letter-spacing: 1px; }
QLabel#BrandSub, QLabel#Eyebrow { color: $subtle; font-size: 10px; font-weight: 650; letter-spacing: 1px; }
QLabel#Logo { background: $primary; color: white; border-radius: 12px; font-size: 21px; font-weight: 700; }
QLabel#PageTitle { font-size: 26px; font-weight: 700; letter-spacing: -0.5px; }
QLabel#PeriodTitle { font-size: 20px; font-weight: 700; }
QLabel#Muted { color: $muted; }
QLabel#DangerText { color: $danger; }
QLabel#SectionTitle { font-size: 15px; font-weight: 650; }
QLabel#EventTitle { font-size: 19px; font-weight: 700; }
QLabel#StatusPill { color: $accent; background: $soft_accent; border-radius: 7px; padding: 6px 9px; }
QFrame#Surface, QFrame#Inspector { background: $surface; border: 1px solid $border; border-radius: 14px; }
QFrame#Metric { background: $surface; border: 1px solid $border; border-radius: 8px; }
QLabel#CardTitle { color: $muted; font-size: 11px; }
QLabel#CardValue { color: $card_value; font-size: 18px; font-weight: 700; }
QPushButton { background: $surface; border: 1px solid $control_border; border-radius: 8px; padding: 9px 13px; font-weight: 600; }
QPushButton:hover { background: $hover; border-color: $hover_border; }
QPushButton:pressed { background: $pressed; }
QPushButton:disabled { color: $disabled_text; border-color: $disabled_border; background: $disabled_surface; }
QPushButton#Primary { background: $primary; border-color: $primary; color: white; }
QPushButton#Primary:hover { background: $primary_hover; }
QPushButton#Primary:disabled { background: $primary_disabled; border-color: $primary_disabled; }
QPushButton#Nav { background: transparent; border: none; text-align: left; color: $nav_text; padding: 12px 15px; }
QPushButton#Nav:hover { background: $nav_hover; }
QPushButton#Nav:checked { color: $accent; background: $soft_accent; font-weight: 700; }
QPushButton#Segment { border: none; background: transparent; padding: 7px 12px; color: $segment_text; }
QPushButton#Segment:checked { background: $surface; color: $segment_selected; border: 1px solid $segment_border; }
QFrame#Segments { background: $segments; border-radius: 9px; }
QPushButton#Arrow { padding: 4px; font-size: 20px; min-width: 28px; }
QPushButton#Danger { color: $danger; }
QPushButton#ThemeToggle { text-align: left; padding: 10px 12px; }
QPushButton#UpdateIndicator { background: $soft_accent; border: 1px solid $hover_border; padding: 4px; }
QPushButton#UpdateIndicator:hover { background: $pressed; border-color: $focus_border; }
QDialog#ReleaseDialog { background: $surface; }
QFrame#ReleaseHero {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0.6, stop:0 $soft_accent, stop:1 $release_tint);
    border: none; border-bottom: 1px solid $segment_border; }
QLabel#ReleaseEyebrow { color: $segment_selected; font-size: 13px; font-weight: 650; }
QLabel#ReleaseTitle { color: $text; font-size: 32px; font-weight: 700; letter-spacing: -0.8px; }
QLabel#ReleaseMeta { color: $secondary_text; font-size: 12px; }
QFrame#ReleaseBody { background: $surface; border: none; }
QLabel#ReleaseSectionTitle { color: $text; font-size: 19px; font-weight: 650; }
QTextEdit#ReleaseNotes { background: $surface; color: $text; font-size: 14px; border: 1px solid transparent;
    padding: 0; selection-background-color: $selection; selection-color: $selection_text; }
QTextEdit#ReleaseNotes:focus { border-color: $focus_border; border-radius: 5px; }
QFrame#ReleaseFooter { background: $background; border: none; border-top: 1px solid $border; }
QLabel#ReleaseState { color: $secondary_text; font-size: 12px; }
QLabel#ReleaseState[attention="true"] { color: $text; font-weight: 600; }
QLabel#ReleasePercent { color: $segment_selected; font-size: 13px; font-weight: 650; }
QProgressBar#ReleaseProgress { background: $segment_border; border-radius: 3px; }
QProgressBar#ReleaseProgress::chunk { background: $accent; border-radius: 3px; }
QDialog#ReleaseDialog QPushButton { min-height: 18px; padding: 8px 17px; font-size: 13px; }
QPushButton#ReleaseLater { background: transparent; border: 1px solid transparent; color: $secondary_text; }
QPushButton#ReleaseLater:hover { background: $hover; color: $text; border-color: $hover_border; }
QPushButton#ReleaseLater:focus { border: 1px solid $focus_border; color: $text; }
QDialog#ReleaseDialog QPushButton#Primary:focus { border: 2px solid $segment_selected; padding: 7px 16px; }
QPushButton#Link { color: $accent; background: transparent; border: none; text-align: left; padding-left: 0; }
QTabWidget::pane { border: none; background: transparent; }
QTabWidget#AnalyticsDetails QTabBar::tab { background: $segments; color: $segment_text; border: none; border-radius: 7px; padding: 9px 16px; margin: 0 5px 8px 0; }
QTabWidget#AnalyticsDetails QTabBar::tab:selected { background: $surface; color: $accent; }
QTabWidget#AnalyticsDetails QTabBar::tab:hover { background: $hover; }
QLabel#UnplannedLegend { color: $unplanned_bar; }
QLineEdit, QPlainTextEdit, QComboBox, QDateTimeEdit, QDateEdit, QSpinBox { background: $surface; border: 1px solid $control_border;
    border-radius: 8px; padding: 7px 10px; min-height: 22px; selection-background-color: $selection; }
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QDateTimeEdit:focus, QDateEdit:focus, QSpinBox:focus { border: 1px solid $focus_border; }
QLineEdit:disabled, QDateTimeEdit:disabled { background: $readonly_surface; color: $readonly_text; }
QLineEdit#Search { background: $surface; padding-left: 12px; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: $surface; border: 1px solid $control_border; selection-background-color: $soft_accent; }
QGroupBox { background: $surface; border: 1px solid $border; border-radius: 12px; margin-top: 17px; padding: 22px 16px 16px; font-weight: 650; }
QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 5px; }
QTabWidget#SettingsTabs::pane { background: $surface; border: 1px solid $border; border-radius: 10px; }
QTabWidget#SettingsTabs QTabBar::tab { background: transparent; color: $secondary_text;
    border: none; border-bottom: 2px solid transparent; padding: 9px 12px; margin: 0 2px 6px 0; font-weight: 600; }
QTabWidget#SettingsTabs QTabBar::tab:hover { color: $text; background: $hover; }
QTabWidget#SettingsTabs QTabBar::tab:selected { color: $segment_selected; border-bottom-color: $accent; }
QTabWidget#SettingsTabs QTabBar::tab:selected:focus { background: $soft_accent; }
QWidget#SettingsContent, QScrollArea#SettingsScroll { background: $surface; }
QWidget#SettingsContent QLabel#Muted, QWidget#SettingsContent QHeaderView::section { color: $secondary_text; }
QFrame#SettingsDivider { background: $border; border: none; max-height: 1px; }
QGroupBox[settingsSection="true"] { background: transparent; border: none; border-radius: 0;
    margin-top: 23px; padding: 0; font-size: 15px; font-weight: 600; }
QGroupBox[settingsSection="true"]::title { subcontrol-origin: margin; subcontrol-position: top left; left: 0; padding: 0; }
QWidget#SettingsContent QPushButton { padding: 6px 11px; }
QWidget#SettingsContent QLineEdit, QWidget#SettingsContent QComboBox, QWidget#SettingsContent QSpinBox {
    min-height: 20px; padding: 5px 9px; }
QTableWidget { background: $surface; alternate-background-color: $table_alternate; border: 1px solid $border; border-radius: 10px;
    gridline-color: $table_grid; selection-background-color: $soft_accent; selection-color: $selection_text; outline: none; }
QTableWidget::item { padding: 7px; border-bottom: 1px solid $table_grid; }
QHeaderView::section { background: $table_header; color: $header_text; border: none; border-bottom: 1px solid $border; padding: 12px 8px; font-size: 11px; font-weight: 600; }
QTableWidget#HistoryTable::item { padding: 3px 8px; border-bottom: 1px solid $table_grid; }
QTableWidget#HistoryTable QHeaderView::section { padding: 7px 8px; color: $secondary_text; }
HistoryPage QLabel#Muted { color: $secondary_text; }
HistoryPage QPushButton#Link:disabled { color: $muted; }
QFrame#HistoryFiltersPanel { background: $surface; border: 1px solid $border; border-radius: 8px; }
QPushButton#HistoryFilters:checked { background: $soft_accent; color: $segment_selected; border-color: $hover_border; }
QPushButton#HistoryPageButton { background: transparent; border: 1px solid transparent; padding: 5px 8px; }
QPushButton#HistoryPageButton:hover:enabled { background: $hover; border-color: $hover_border; }
QPushButton#HistoryPageButton:focus { border-color: $focus_border; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: transparent; width: 7px; margin: 2px; }
QScrollBar::handle:vertical { background: $scrollbar; border-radius: 3px; min-height: 30px; }
QScrollBar:horizontal { background: transparent; height: 7px; }
QScrollBar::handle:horizontal { background: $scrollbar; border-radius: 3px; min-width: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QCheckBox { spacing: 9px; font-weight: 400; }
QCheckBox::indicator { width: 15px; height: 15px; }
QToolTip { background: $tooltip; color: #FFFFFF; border: none; padding: 8px; font-size: 12px; }
QMenu { background: $surface; border: 1px solid $control_border; color: $text; }
QMenu::item:selected { background: $soft_accent; }
QMenu#EventContextMenu { background: $surface; border: 1px solid $control_border; border-radius: 9px; padding: 6px; }
QMenu#EventContextMenu::item { padding: 9px 20px 9px 28px; border-radius: 6px; }
QMenu#EventContextMenu::item:disabled { color: $muted; }
QMenu#EventContextMenu::separator { height: 1px; background: $border; margin: 4px 10px; }
QCalendarWidget#MiniCalendar, QWidget#MiniCalendarHeader { background: $surface; }
QWidget#DatePickerPopup { background: transparent; border: none; }
QCalendarWidget#MiniCalendar[datePopup="true"] { border: 1px solid $popup_border; border-radius: 12px; background: $surface; }
QCalendarWidget#MiniCalendar QWidget { alternate-background-color: $surface; }
QToolButton#MiniArrow { background: transparent; border: 1px solid transparent; border-radius: 7px; padding: 0; }
QToolButton#MiniArrow:hover, QToolButton#MiniArrow:focus { background: $soft_accent; border-color: $mini_hover_border; }
QToolButton#MiniArrow:pressed { background: $mini_pressed; }
QToolButton#MiniMonth { color: $mini_heading; background: transparent; border: none; border-radius: 7px;
    font-size: 11px; font-weight: 650; padding: 5px 2px; }
QToolButton#MiniMonth:hover, QToolButton#MiniMonth:focus { color: $accent; background: $mini_heading_hover; }
QCalendarWidget#MiniCalendar QAbstractItemView { background: $surface; alternate-background-color: $surface;
    color: $mini_header; border: none; outline: none; font-size: 10px; selection-background-color: transparent; }
QMenu#MiniCalendarMenu { background: $surface; border: 1px solid $control_border; border-radius: 9px; padding: 6px; }
QMenu#MiniCalendarMenu::item { padding: 7px 20px 7px 25px; border-radius: 5px; }
QMenu#MiniCalendarMenu::item:selected { background: $soft_accent; color: $segment_selected; }
QMenu#MiniCalendarMenu::separator { height: 1px; background: $border; margin: 4px 8px; }
QLabel#PlanLegend { color: $plan_legend; }
QLabel#ActualLegend { color: $actual_legend; }
QProgressBar { background: $progress; border: none; border-radius: 3px; height: 5px; text-align: center; }
QProgressBar::chunk { background: $accent; border-radius: 3px; }
"""

def current_theme():
    app = QApplication.instance()
    return "dark" if app and app.property("ui_theme") == "dark" else "light"


def is_dark():
    return current_theme() == "dark"


def color(token):
    return QColor((DARK if is_dark() else LIGHT)[token])


def stylesheet(name="light"):
    return Template(_STYLE_TEMPLATE).substitute(DARK if name == "dark" else LIGHT)


# Retain the light stylesheet for callers that explicitly request it.
STYLE = stylesheet("light")


def apply_theme(name):
    """Apply to native controls and repaint existing custom widgets immediately."""
    name = "dark" if name == "dark" else "light"
    app = QApplication.instance()
    if app is None:
        return name
    sheet = stylesheet(name)
    if app.property("ui_theme") == name and app.styleSheet() == sheet:
        return name
    app.setProperty("ui_theme", name)
    tokens = DARK if name == "dark" else LIGHT
    palette = QPalette()
    roles = {
        QPalette.ColorRole.Window: "background", QPalette.ColorRole.WindowText: "text",
        QPalette.ColorRole.Base: "surface", QPalette.ColorRole.AlternateBase: "table_alternate",
        QPalette.ColorRole.Text: "text", QPalette.ColorRole.Button: "surface",
        QPalette.ColorRole.ButtonText: "text", QPalette.ColorRole.Highlight: "selection",
        QPalette.ColorRole.HighlightedText: "text", QPalette.ColorRole.ToolTipBase: "tooltip",
        QPalette.ColorRole.Link: "accent", QPalette.ColorRole.PlaceholderText: "muted",
        QPalette.ColorRole.Light: "control_border", QPalette.ColorRole.Mid: "border",
        QPalette.ColorRole.Dark: "background", QPalette.ColorRole.Shadow: "background",
    }
    for role, token in roles.items():
        palette.setColor(role, QColor(tokens[token]))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("white"))
    palette.setColor(QPalette.ColorRole.BrightText, QColor("white"))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText, QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(tokens["disabled_text"]))
    app.setPalette(palette)
    # Qt delivers palette/style changes and repaints existing widgets itself.
    # Avoid enumerating native popup widgets while Qt may be destroying them.
    app.setStyleSheet(sheet)
    return name



_PATHS = {
    "download": '<path d="M12 3v12m-5-5 5 5 5-5M4 16v4h16v-4"/>',
    "moon": '<path d="M20.5 13A8.5 8.5 0 0 1 11 3.5 8.5 8.5 0 1 0 20.5 13z"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/>',
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


def icon(name, color=None):
    color = color or (DARK if is_dark() else LIGHT)["accent"]
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><g fill="none" stroke="{color}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{_PATHS[name]}</g></svg>'
    pixmap = QPixmap(48, 48)
    pixmap.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)
