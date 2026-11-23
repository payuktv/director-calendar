from dataclasses import replace

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QApplication, QDialog

from director_control.mail_review_ui import MailReviewDialog
from director_control.storage import Store
from director_control.ui import EventDialog, MainWindow
from tests.test_mail_calendar import CONFIG, event, parse


def test_sync_summary_and_settings_open_matching_events_and_update_after_edit(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    store = Store(tmp_path / 'mail.db')
    for key, value in [('mail_url', CONFIG.url), ('mail_login', CONFIG.username), ('mail_auto', '0')]:
        store.set_setting(key, value)
    initial = parse(event('missing'), event('conflict', start='20261022T150000Z', end='20261022T153000Z'))
    store.apply_calendar_snapshot(initial)
    missing, conflict = store.daily_events('2026-10-22')
    store.freeze_day('2026-10-22')
    store.update_event(conflict.id, status='done')
    window = MainWindow(store)
    seen = []
    try:
        window.show()
        assert not window.mail_review_button.isVisible()
        cancelled = replace(initial.events[1], cancelled=True)
        window.mail_panel.apply_snapshot(replace(initial, events=(cancelled,)))
        assert window.mail_status.isVisible()
        assert window.mail_review_button.text() == 'Требуют проверки · 2'

        def inspect(dialog):
            table = dialog.table
            assert [table.item(row, 1).text() for row in range(2)] == [missing.title, missing.title]
            assert [table.item(row, 1).data(Qt.ItemDataRole.UserRole) for row in range(2)] == [missing.id, conflict.id]
            assert table.item(0, 0).text() == '22.10.2026 12:00–13:00'
            assert table.item(0, 3).text() == 'Нет в ответе Mail.ru'
            assert table.item(1, 2).text() == 'Выполнено'
            assert table.item(1, 3).text() == 'Отменено в Mail.ru'
            return QDialog.DialogCode.Rejected

        monkeypatch.setattr(MailReviewDialog, 'exec', inspect)
        window.mail_review_button.click()
        window.close()
        window.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)

        window = MainWindow(store)
        window.show()
        assert window.mail_review_button.isVisible()
        window.nav_buttons[3].click()
        window.settings_tabs.setCurrentIndex(2)
        assert not window.mail_review_button.isVisible()
        assert window.mail_panel.review_button.isVisible()
        assert window.mail_panel.review_button.text() == 'Требуют проверки · 2'

        def edit(card):
            seen.append(card._event.id)
            card.status_input.setCurrentIndex(card.status_input.findData('cancelled'))
            card.save()
            return card.result()

        def resolve(dialog):
            dialog.table.setCurrentCell(1, 1)
            dialog.open_button.click()
            assert dialog.table.rowCount() == 1
            assert dialog.table.item(0, 1).data(Qt.ItemDataRole.UserRole) == missing.id
            dialog.open_button.click()
            assert dialog.table.rowCount() == 0 and not dialog.empty.isHidden()
            assert not dialog.open_button.isEnabled()
            return QDialog.DialogCode.Rejected

        monkeypatch.setattr(EventDialog, 'exec', edit)
        monkeypatch.setattr(MailReviewDialog, 'exec', resolve)
        window.mail_panel.review_button.click()
        assert seen == [conflict.id, missing.id]
        assert not window.mail_panel.review_button.isVisible()
        window.nav_buttons[0].click()
        assert not window.mail_review_button.isVisible()
    finally:
        window.close()
        window.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_review_opens_older_card_with_only_an_original_all_day_plan(tmp_path):
    app = QApplication.instance() or QApplication([])
    store = Store(tmp_path / 'mail.db')
    initial = parse('UID:day\nDTSTART;VALUE=DATE:20261022\nDTEND;VALUE=DATE:20261024\nSUMMARY:Conference')
    store.apply_calendar_snapshot(initial)
    store.freeze_day('2026-10-22')
    store.apply_calendar_snapshot(replace(initial, events=()))
    record = store.daily_events('2026-10-22')[0]
    with store._connect() as con:
        con.execute('UPDATE events SET current_start=NULL, current_end=NULL WHERE id=?', (record.id,))
    review = MailReviewDialog(store, CONFIG.calendar_key)
    card = EventDialog(store, store.get_event(record.id))
    try:
        assert review.table.item(0, 0).text() == '22.10.2026 · весь день'
        assert '23.10.2026' in review.table.item(0, 0).toolTip()
        assert card.start_input.text() == 'не заполнено'
        assert not card.fact_checkbox.isChecked()
        assert store.get_event(record.id).current_start is None
    finally:
        for dialog in (review, card):
            dialog.close()
            dialog.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
