"""Exercise OS language detection, stored preferences, and bilingual calendar data."""
import csv
import json
from datetime import datetime
from string import Formatter

import pytest
from PySide6.QtCore import QDate, QEvent, QLocale, Qt
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
                expected = 'Settings' if new == 'en' else 'Настройки'
                assert window.nav_buttons[3].text() == window.page_title.text() == expected
                assert window.tabs.currentIndex() == 3 and window.isVisible()
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


@pytest.fixture
def live_window(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = MainWindow(Store(tmp_path / 'live.db'))
    window.show()
    app.processEvents()
    yield window
    window.close()
    app.processEvents()
    window.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def choose(window, language):
    window.language_input.setCurrentIndex(window.language_input.findData(language))


def test_live_switch_keeps_calendar_selection_and_unsaved_fields(live_window):
    w = live_window
    day = QDate(2026, 11, 5)
    w.set_date(day)
    w.set_view('agenda')
    event_id = w.store.create_event('Выполнено', 'Работа', '2026-11-05T09:00', '2026-11-05T10:00', note='Settings')
    w.store.add_category('Отмена')
    w.search.setText('Work')
    w.select_event(event_id)
    w.tabs.setCurrentIndex(3)
    w.new_category.setText('Сохранить')
    w.mail_panel.login.setText('draft@example.test')
    w.mail_panel.password.setText('synthetic draft')
    w.backup_panel.folder.setText('Отмена')
    w.tolerance.setValue(42)
    w.mini.setCurrentPage(2027, 3)
    before = w.store.audit_log()
    for lang, settings, title, category, month in [
        ('en', 'Settings', 'Event', 'Work', 'March'), ('ru', 'Настройки', 'Мероприятие', 'Работа', 'Март'),
    ]:
        choose(w, lang)
        assert w.tabs.currentIndex() == 3 and w.page_title.text() == settings
        assert w.date_input.date() == day and w.mode == 'agenda' and w.search.text() == 'Work'
        assert w.selected_event_id() == event_id and w.inspector.title.text() == 'Выполнено'
        assert w.table.horizontalHeaderItem(0).text() == title
        assert w.table.item(0, 0).text() == 'Выполнено' and w.table.item(0, 1).text() == category
        categories = {w.category_table.item(i, 0).data(Qt.ItemDataRole.UserRole): w.category_table.item(i, 0).text()
                      for i in range(w.category_table.rowCount())}
        assert categories['Работа'] == category and categories['Отмена'] == 'Отмена'
        assert month in w.mini.month_button.text()
        assert w.language_input.currentData() == lang and w.new_category.text() == 'Сохранить'
        assert w.mail_panel.login.text() == 'draft@example.test' and w.mail_panel.password.text() == 'synthetic draft'
        assert w.backup_panel.folder.text() == 'Отмена' and w.tolerance.value() == 42
        assert w.analytics_page.event_filter.itemText(0) == ('All events' if lang == 'en' else 'Все события')
        assert w.history_page.page_size.currentText() == ('Show 100' if lang == 'en' else 'По 100')
    assert w.store.audit_log() == before


def test_switch_during_sync_keeps_worker_and_renders_result_in_current_language(live_window, monkeypatch):
    from threading import Event
    from PySide6.QtTest import QTest
    from director_control import mail_ui
    from director_control.mail_calendar import CalendarSnapshot

    w = live_window
    panel = w.mail_panel
    started, finish = Event(), Event()

    def fetch(config, password, start, end, *, cancelled):
        started.set()
        assert finish.wait(10) and not cancelled()
        return CalendarSnapshot(config.calendar_key, start.isoformat() + 'T00:00:00', end.isoformat() + 'T00:00:00', (), ())

    monkeypatch.setattr(mail_ui, 'fetch_snapshot', fetch)
    monkeypatch.setattr(panel.credentials, 'get', lambda key: 'synthetic')
    w.store.set_setting('mail_url', 'https://calendar.mail.ru/test/')
    w.store.set_setting('mail_login', 'synthetic@example.test')
    w.tabs.setCurrentIndex(3)
    panel.sync()
    worker = panel.worker
    try:
        assert started.wait(5)
        choose(w, 'en')
        assert panel.worker is worker and worker.isRunning()
        assert panel.status.text() == w.mail_status.text() == 'Syncing the Mail.ru calendar…'
        assert not w.mail_refresh.isEnabled()
    finally:
        finish.set()
        if worker is not None:
            assert worker.wait(5000)
        QTest.qWait(30)
    assert not panel.busy and w.mail_refresh.isEnabled()
    assert panel.status.text().startswith('Mail.ru synced ')
    choose(w, 'ru')
    assert w.mail_status.text() == panel.status.text() and panel.status.text().startswith('Mail.ru обновлён ')


def test_switch_during_backup_keeps_worker_schedule_and_draft(live_window, monkeypatch):
    from threading import Event
    from PySide6.QtTest import QTest
    from director_control import backup_ui
    panel = live_window.backup_panel
    started, finish = Event(), Event()

    def backup(store):
        started.set()
        assert finish.wait(10)

    monkeypatch.setattr(backup_ui, 'scheduled_backup', backup)
    panel.timer.start(900000)
    timer_id = panel.timer.timerId()
    panel.folder.setText('draft folder')
    panel._start('auto')
    worker = panel.worker
    try:
        assert started.wait(5)
        choose(live_window, 'en')
        assert panel.worker is worker and worker.isRunning()
        assert panel.timer.timerId() == timer_id and panel.folder.text() == 'draft folder'
        assert panel.status.text() == 'Checking and saving backup…' and not panel.folder.isEnabled()
    finally:
        finish.set()
        assert worker.wait(5000)
        QTest.qWait(30)
    assert not panel.busy and panel.folder.isEnabled()
    assert panel.status.text().startswith('Last automatic backup:')


def test_switch_updates_open_release_notes_and_preserves_download(live_window, monkeypatch):
    from director_control import update_check
    from tests.test_update_check import payload, release_data
    w = live_window
    w.tabs.setCurrentIndex(3)
    panel = w.update_panel
    panel.supported = True
    data = release_data('5.0.0')
    data['body'] = '# v5.0.0\n\nEnglish release notes\n\n## Что нового\n\nОписание выпуска'
    panel._result(update_check.parse_release(payload(data)))
    dialog = panel.dialog
    assert dialog.isVisible() and dialog.description.toPlainText() == 'Описание выпуска'
    russian_state = dialog.eyebrow.text()
    choose(w, 'en')
    assert panel.dialog is dialog and dialog.isVisible()
    assert dialog.windowTitle() == 'Application update'
    assert dialog.eyebrow.text() and dialog.eyebrow.text() != russian_state
    assert dialog.description.toPlainText() == 'English release notes' and dialog.confirm.text() == 'Download update'
    downloads = []
    preparer = panel.preparer
    monkeypatch.setattr(preparer, 'start', downloads.append)
    monkeypatch.setattr(type(preparer), 'busy', property(lambda self: bool(downloads)))
    dialog.confirm.click()
    panel.progress.setValue(41)
    choose(w, 'ru')
    assert downloads == [panel.release.package] and panel.progress.value() == 41 and not dialog.isVisible()
    assert w.update_indicator.toolTip() == 'Загружается версия 5.0.0'
    assert panel.status.text() == 'Загружаем и проверяем версию 5.0.0…'
    panel.show_details()
    assert dialog.description.toPlainText() == 'Описание выпуска' and dialog.confirm.isHidden()
    assert dialog.progress.isVisible() and dialog.progress.value() == 41
    dialog.reject()


def test_language_write_failure_preserves_active_ui(live_window, monkeypatch):
    from director_control import ui
    window = live_window
    errors = []
    monkeypatch.setattr(ui, 'error_box', lambda parent, exc: errors.append(str(exc)))

    def unavailable(key, value):
        raise OSError('Synthetic write failure')

    monkeypatch.setattr(window.store, 'set_setting', unavailable)
    choose(window, 'en')
    assert errors == ['Synthetic write failure']
    assert window.language_input.currentData() == 'auto' and i18n.current_language() == 'ru'
    assert window.nav_buttons[3].text() == 'Настройки'


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
