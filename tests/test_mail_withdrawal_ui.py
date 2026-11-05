"""Withdrawn source records remain inspectable through History."""
from dataclasses import replace

from PySide6.QtWidgets import QApplication, QDateTimeEdit, QDialog, QDialogButtonBox, QLabel

from director_control.history_ui import HistoryEntryDialog
from director_control.storage import Store
from director_control.ui import EventDialog, MainWindow
from tests.test_mail_withdrawal import snapshot


def test_history_opens_withdrawn_record_without_inventing_times(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    store = Store(tmp_path/'db')
    initial = snapshot('old')
    store.apply_calendar_snapshot(initial)
    original = store.daily_events('2099-10-22')[0]
    store.apply_calendar_snapshot(replace(initial, events=()))
    withdrawn = store.get_event(original.id)
    record = next(row for row in store.audit_log() if row['event_id'] == original.id)
    history = HistoryEntryDialog(store, record)
    assert history.open_button.isEnabled()
    dialog = EventDialog(store, withdrawn)
    assert not dialog.findChildren(QDateTimeEdit)
    assert any('Прежнее время' in label.text() for label in dialog.findChildren(QLabel))
    buttons = dialog.findChild(QDialogButtonBox)
    assert buttons.button(QDialogButtonBox.StandardButton.Save) is None
    assert buttons.button(QDialogButtonBox.StandardButton.Close).isEnabled()
    opened = []
    monkeypatch.setattr(EventDialog, 'exec', lambda self: opened.append(self) or QDialog.DialogCode.Rejected)
    window = MainWindow(store)
    window.open_event(original.id)
    assert len(opened) == 1
    assert store.get_event(original.id) == withdrawn
    for widget in (history, dialog, window, *opened):
        widget.close()
        widget.deleteLater()
    app.processEvents()
