"""Exercise OS language detection, stored preferences, and bilingual calendar data."""
import csv
import json
from datetime import datetime
from string import Formatter

import pytest
from PySide6.QtCore import QDate, QEvent, QLocale
from PySide6.QtWidgets import QApplication, QDialogButtonBox

from director_control import i18n
from director_control.english import MESSAGES
from director_control.history import describe
from director_control.i18n import system_language
from director_control.local_event_dialog import LocalEventDialog
from director_control.storage import Store
from director_control.ui import MainWindow
from director_control.update_check import release_description


@pytest.fixture(autouse=True)
def restore_language():
    yield
    i18n.configure_widgets('ru')


@pytest.mark.parametrize(('system', 'expected'), [
    ('ru-Cyrl-RU', 'ru'), ('ru_KZ', 'ru'), ('en-US', 'en'), ('de-DE', 'en'), ('C', 'en'),
])
def test_automatic_uses_primary_display_language(monkeypatch, system, expected):
    monkeypatch.setattr(i18n, 'system_language', lambda: system)
    assert i18n.select_language('auto') == expected
    assert i18n.select_language('ru') == 'ru'
    assert i18n.select_language('en') == 'en'


def test_os_display_language_takes_priority_over_region(monkeypatch):
    class SystemLocale:
        def uiLanguages(self):
            return ['en-US', 'ru-RU']

        def name(self):
            return 'ru_RU'

    monkeypatch.setattr(QLocale, 'system', SystemLocale)
    assert system_language() == 'en-US'
    monkeypatch.setattr(SystemLocale, 'uiLanguages', lambda self: [])
    assert system_language() == 'ru_RU'


def test_choice_survives_reopening_and_can_follow_system_again(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    path = tmp_path / 'existing.db'
    store = Store(path)
    store.create_event('Выполнено', 'Работа', '2026-11-05T09:00', '2026-11-05T10:00', note='Отмена')
    before = store.audit_log()
    monkeypatch.setattr(i18n, 'system_language', lambda: 'de-DE')
    for saved, tabs, new in [
        ('auto', ['Calendar', 'Analytics', 'History', 'Settings'], 'ru'),
        ('ru', ['Календарь', 'Аналитика', 'История', 'Настройки'], 'en'),
        ('en', ['Calendar', 'Analytics', 'History', 'Settings'], 'auto'),
        ('auto', ['Календарь', 'Аналитика', 'История', 'Настройки'], None),
    ]:
        if new == 'auto' or new is None:
            monkeypatch.setattr(i18n, 'system_language', lambda: 'ru-RU')
        window = MainWindow(Store(path))
        try:
            window.show()
            app.processEvents()
            window.tabs.setCurrentIndex(3)
            assert window.language_input.currentData() == saved
            assert [button.text() for button in window.nav_buttons] == tabs
            assert window.page_title.text() == tabs[-1]
            language = 'en' if tabs[0] == 'Calendar' else 'ru'
            assert window.language_input.itemText(0) == ('Automatic' if language == 'en' else 'Автоматически')
            assert window.language_input.itemText(1) == 'Русский'
            assert window.language_input.itemText(2) == 'English'
            window.date_input.setDate(QDate(2026, 11, 5))
            assert ('November' if language == 'en' else 'ноября') in window.period_title.text()
            assert window.mini.locale().name().startswith(language)
            assert QLocale().name().startswith(language)
            assert window.update_panel.check_button.text() == ('Check for updates' if language == 'en' else 'Проверить обновления')
            if new:
                window.language_input.setCurrentIndex(window.language_input.findData(new))
                assert store.get_setting('ui_language') == new
        finally:
            window.close()
            app.processEvents()
            window.deleteLater()
            app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert store.audit_log() == before


def test_english_editor_export_and_history_preserve_user_data(tmp_path):
    app = QApplication.instance() or QApplication([])
    i18n.configure_widgets('en')
    store = Store(tmp_path / 'test.db')
    store.add_category('Отмена')
    start = datetime(2026, 11, 5, 9)
    event_id = store.create_event('Выполнено', 'Работа', start.isoformat(), '2026-11-05T10:00', note='Отменено')
    dialog = LocalEventDialog(store, start, store.get_event(event_id))
    try:
        assert dialog.title_input.text() == 'Выполнено'
        assert dialog.note_input.toPlainText() == 'Отменено'
        assert dialog.category_input.currentText() == 'Work'
        assert dialog.category_input.currentData() == 'Работа'
        assert dialog.category_input.itemText(dialog.category_input.findData('Отмена')) == 'Отмена'
        dialog.status_input.setCurrentIndex(dialog.status_input.findData('done'))
        assert dialog.status_input.currentText() == 'Completed'
        dialog.save()
        assert dialog._saved
    finally:
        dialog.close()
        dialog.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    event = store.get_event(event_id)
    assert (event.title, event.note, event.category, event.status) == ('Выполнено', 'Отменено', 'Работа', 'done')
    destination = tmp_path / 'plan.csv'
    store.export_csv('2026-11-05', destination)
    with destination.open(encoding='utf-8-sig', newline='') as stream:
        row, = csv.DictReader(stream, delimiter=';')
    assert (row['Event'], row['Category'], row['Status'], row['Notes']) == ('Выполнено', 'Work', 'Completed', 'Отменено')
    assert store.audit_page(search='completed').total
    data = json.dumps({'status': {'было': 'pending', 'стало': 'done'}, 'title': 'Выполнено'})
    assert describe('Изменение', data).details == 'Status: Unconfirmed → Completed\nTitle: Выполнено'
    i18n.configure_widgets('ru')
    assert 'Не подтверждено → Выполнено' in describe('Изменение', data).details


def test_update_notes_and_standard_dialog_buttons_follow_language():
    app = QApplication.instance() or QApplication([])
    notes = '# v1.5.0\n\n- English notes\n\n## Что нового\n\n- Русское описание\n\nSource commit: abc'
    for choice, expected in [('ru', 'Русское описание'), ('en', 'English notes')]:
        i18n.configure_widgets(choice)
        assert release_description(notes) == '• ' + expected
        assert release_description('## Что нового\n- Только русский') == '• Только русский'
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        assert buttons.button(QDialogButtonBox.StandardButton.Cancel).text().replace('&', '') == (
            'Cancel' if choice == 'en' else 'Отмена')
        buttons.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_catalog_preserves_format_fields_and_covers_event_statuses():
    from director_control.event_status import STATUSES
    formatter = Formatter()
    for source, target in MESSAGES.items():
        assert target.strip()
        assert sorted((name, spec, conv) for _, name, spec, conv in formatter.parse(source) if name is not None) == sorted(
            (name, spec, conv) for _, name, spec, conv in formatter.parse(target) if name is not None)
    assert set(STATUSES.values()) <= MESSAGES.keys()
