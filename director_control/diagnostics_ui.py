"""Local log access and a queued, non-modal notice for unhandled Python errors."""
from PySide6.QtCore import QObject, Signal, Slot, QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QGroupBox, QHBoxLayout, QMessageBox, QPushButton, QVBoxLayout

from .widget_text import localized
from .i18n import tr
from . import diagnostics
from .inspector import plain_label, text_label


class ErrorNotice(QObject):
    raised = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.message = None
        self.raised.connect(self.show_error, Qt.ConnectionType.QueuedConnection)

    @Slot(bool)
    def show_error(self, written):
        try:
            self._show_error(written)
        except Exception as exc:
            diagnostics.record_error('ui.action', exc)

    def _show_error(self, written):
        if self.message is not None and self.message.isVisible():
            return
        self.message = QMessageBox(QMessageBox.Icon.Warning, tr('Ошибка приложения'),
            tr('Возникла непредвиденная ошибка. Последнее действие могло не завершиться. '
            'Проверь результат и перезапусти приложение.\n\n') +
            (tr('Диагностика сохранена в журнале. Он доступен в Настройках → Диагностика.') if written else
             tr('Не удалось записать диагностику. Проверь доступ и свободное место в папке данных.')))
        self.message.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.message.finished.connect(self._closed)
        self.message.open()

    def _closed(self, *_):
        self.message = None


class DiagnosticsPanel(QGroupBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        localized(self, title='Диагностика')
        self.setProperty('settingsSection', True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        self.path_label = plain_label(str(diagnostics.log_path()))
        self.path_label.setWordWrap(True)
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.path_label)
        note = text_label('Журнал хранит тип ошибки и место в коде: без текстов ошибок, паролей и содержимого календаря. '
                           'До четырёх файлов по 1 МБ; старые записи заменяются автоматически. '
                           'Файлы никуда не отправляются.', 'Muted')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.status = plain_label('')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        row = QHBoxLayout()
        self.open_button = localized(QPushButton(), text='Открыть папку журнала')
        self.open_button.clicked.connect(self.open_folder)
        row.addWidget(self.open_button)
        self.copy_button = localized(QPushButton(), text='Скопировать путь')
        self.copy_button.clicked.connect(self.copy_path)
        row.addWidget(self.copy_button)
        row.addStretch()
        layout.addLayout(row)

    def showEvent(self, event):
        self.path_label.setText(str(diagnostics.log_path()))
        localized(self.status, text='Журнал доступен.' if diagnostics.available() else
                  'Журнал недоступен. Проверь доступ и свободное место в папке данных.')
        super().showEvent(event)

    def open_folder(self):
        folder = diagnostics.log_path().parent
        try:
            if not folder.is_dir() or not QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))):
                raise OSError('Cannot open diagnostics directory')
        except Exception as exc:
            diagnostics.record_error('diagnostics.open', exc)
            localized(self.status, text='Не удалось открыть папку. Скопируй путь и открой её через Проводник.')

    def copy_path(self):
        QApplication.clipboard().setText(str(diagnostics.log_path()))
        localized(self.status, text='Путь к журналу скопирован.')
