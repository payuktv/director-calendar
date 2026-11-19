"""Keep translation sources on their widgets so language changes preserve live UI state."""
from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtWidgets import QComboBox, QDateTimeEdit, QCalendarWidget, QTabWidget, QWidget

from .i18n import tr, ui_locale
from .english import MESSAGES


class Message:
    """Only the template is translated. Values such as filenames and dates stay literal."""
    def __init__(self, source, *values):
        self.source = source
        self.values = values

    def render(self):
        return tr(self.source).format(*(v.render() if isinstance(v, Message) else v for v in self.values))


def render(source):
    return source.render() if isinstance(source, Message) else tr(source)


_DIAGNOSTIC_SOURCES = {translation: source for source, translation in MESSAGES.items() if '{' not in source}


def diagnostic_message(text):
    """Standard errors can arrive already rendered by a worker. Keep external details verbatim."""
    source = _DIAGNOSTIC_SOURCES.get(text, text)
    return Message(source) if source in MESSAGES and '{' not in source else Message('{0}', text)


def localized(widget, **properties):
    """Bind explicitly owned UI properties, such as text, title or placeholderText."""
    sources = widget.property('_director_text') or {}
    sources.update(properties)
    widget.setProperty('_director_text', sources)
    for name, source in properties.items():
        widget.setProperty(name, render(source))
    return widget


def text_source(label):
    return label.property('_director_text')['text']


def add_choice(combo, source, value):
    combo.setProperty('_director_choices', True)
    combo.addItem(render(source), value)
    combo.setItemData(combo.count() - 1, source, Qt.ItemDataRole.UserRole + 1)


def add_tab(tabs, page, source):
    page.setProperty('_director_tab', source)
    tabs.addTab(page, tr(source))


def set_headers(table, sources):
    table.setProperty('_director_headers', sources)
    table.setHorizontalHeaderLabels([tr(source) for source in sources])


def form_row(form, source, field):
    form.addRow(tr(source), field)
    localized(form.labelForField(field), text=source)


def retranslate_widgets(root):
    locale = ui_locale()
    root.setLocale(locale)
    for widget in (root, *root.findChildren(QWidget)):
        for name, source in (widget.property('_director_text') or {}).items():
            widget.setProperty(name, render(source))
        if isinstance(widget, (QDateTimeEdit, QCalendarWidget)):
            widget.setLocale(locale)
        elif isinstance(widget, QComboBox) and widget.property('_director_choices'):
            with QSignalBlocker(widget):
                for i in range(widget.count()):
                    source = widget.itemData(i, Qt.ItemDataRole.UserRole + 1)
                    if isinstance(source, (str, Message)):
                        widget.setItemText(i, render(source))
        elif isinstance(widget, QTabWidget):
            for i in range(widget.count()):
                source = widget.widget(i).property('_director_tab')
                if source:
                    widget.setTabText(i, tr(source))
        headers = widget.property('_director_headers')
        if headers:
            widget.setHorizontalHeaderLabels([tr(source) for source in headers])
