import copy
import json
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtNetwork import QNetworkReply, QNetworkRequest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from director_control import update_check as updates


@pytest.fixture(scope='session')
def app():
    return QApplication.instance() or QApplication([])


def release_data(version='1.0.3'):
    root = updates.REPOSITORY_URL
    return {'tag_name': f'v{version}', 'draft': False, 'prerelease': False,
            'published_at': '2026-11-17T12:00:00Z',
            'html_url': f'{root}/releases/tag/v{version}',
            'assets': [{'name': f'DirectorCalendar-{version}-portable-x64.zip', 'state': 'uploaded',
                        'size': 51000000, 'digest': 'sha256:' + 'a' * 64,
                        'browser_download_url': f'{root}/releases/download/v{version}/DirectorCalendar-{version}-portable-x64.zip'}]}


def payload(data=None):
    return json.dumps(release_data() if data is None else data).encode()


def test_numeric_versions_and_verified_package_are_preserved():
    release = updates.parse_release(payload(release_data('1.10.0')))
    assert updates.version_key(release.version) > updates.version_key('1.9.9')
    assert release.package.url.endswith('/v1.10.0/DirectorCalendar-1.10.0-portable-x64.zip')
    assert (release.package.size, release.package.sha256) == (51000000, 'a' * 64)


@pytest.mark.parametrize('body, text', [
    (None, 'Описание изменений пока не опубликовано.'),
    ('# v1.2.3\n\nFixed the calendar.\n\nSource commit: abc', 'Fixed the calendar.'),
    ('## Что нового\n- План\n- Отчёты\n\n## Installation\nEnglish', '• План\n• Отчёты'),
])
def test_release_description_has_published_changes_or_a_clear_fallback(body, text):
    assert updates.release_description(body) == text


@pytest.mark.parametrize('version', ['v1.2.3', '01.2.3', '1.2', '1.2.3-rc1', '1.2.3+build',
                                     '1.2.3\n', '1.2.-1', '1.2.1234567890', True, None])
def test_invalid_versions_are_rejected(version):
    with pytest.raises(ValueError):
        updates.version_key(version)


@pytest.mark.parametrize('patch', [{'draft': True}, {'prerelease': True}, {'published_at': None},
                                  {'tag_name': '1.0.3'}, {'html_url': 'https://evil.example/'},
                                  {'assets': []}, {'draft': 0}, {'prerelease': 0}])
def test_unpublished_or_incomplete_release_is_rejected(patch):
    data = release_data()
    data.update(patch)
    with pytest.raises(ValueError):
        updates.parse_release(payload(data))


@pytest.mark.parametrize('url', ['http://github.com/payuktv/director-calendar/releases/tag/v1.0.3',
                                'https://github.com.evil.example/install.exe', 'file:///C:/malware.exe',
                                'https://github.com/payuktv/other/releases/download/v1.0.3/setup.exe'])
def test_arbitrary_download_targets_are_rejected(url):
    data = release_data()
    data['assets'][0]['browser_download_url'] = url
    with pytest.raises(ValueError):
        updates.parse_release(payload(data))


@pytest.mark.parametrize('patch', [{'size': 0}, {'size': True}, {'state': 'new'}, {'size': 2**30},
                                   {'digest': None}, {'digest': 'md5:' + 'a'*32}, {'digest': 'sha256:' + 'X'*64}])
def test_unfinished_assets_are_rejected(patch):
    data = release_data()
    data['assets'][0].update(patch)
    with pytest.raises(ValueError):
        updates.parse_release(payload(data))


def test_ambiguous_package_is_rejected():
    data = release_data()
    data['assets'].append(copy.deepcopy(data['assets'][0]))
    with pytest.raises(ValueError):
        updates.parse_release(payload(data))


@pytest.mark.parametrize('data', [b'[]', b'null', b'{', b'\xff', b'x' * (updates.MAX_RESPONSE_BYTES + 1)])
def test_malformed_and_oversized_responses_are_rejected(data):
    with pytest.raises(ValueError):
        updates.parse_release(data)


class Reply(QObject):
    readyRead = Signal()
    finished = Signal()

    def __init__(self, status=200, error=QNetworkReply.NetworkError.NoError):
        super().__init__()
        self.status, self.code = status, error
        self.pending = bytearray()
        self.aborted = False
        self.buffer_limit = None

    def setReadBufferSize(self, value):
        self.buffer_limit = value

    def read(self, size):
        result = self.pending[:size]
        del self.pending[:size]
        return bytes(result)

    def attribute(self, attribute):
        assert attribute == QNetworkRequest.Attribute.HttpStatusCodeAttribute
        return self.status

    def error(self):
        return self.code

    def abort(self):
        self.aborted = True
        self.code = QNetworkReply.NetworkError.OperationCanceledError
        self.finished.emit()

    def feed(self, data, *, finish=True):
        self.pending.extend(data)
        self.readyRead.emit()
        if finish:
            self.finished.emit()


class Manager:
    def __init__(self, reply):
        self.reply, self.requests = reply, []

    def get(self, request):
        self.requests.append(request)
        return self.reply


def checker_for(reply):
    checker = updates.UpdateChecker(manager=Manager(reply))
    good, bad = [], []
    checker.succeeded.connect(good.append)
    checker.failed.connect(bad.append)
    return checker, good, bad


def test_network_backend_is_created_only_for_requested_check(app, monkeypatch):
    created = []
    def factory(parent):
        created.append(parent)
        return Manager(Reply())
    monkeypatch.setattr(updates, 'QNetworkAccessManager', factory)
    checker = updates.UpdateChecker()
    assert created == []
    checker.start()
    assert created == [checker]
    checker.cancel()
    checker.manager.reply = Reply()
    checker.start()
    assert created == [checker]
    checker.cancel()


def test_explicit_single_request_without_credentials_cookies_or_redirects(app):
    reply = Reply()
    checker, good, bad = checker_for(reply)
    assert not checker.manager.requests
    checker.start()
    checker.start()
    assert checker.busy and len(checker.manager.requests) == 1
    request = checker.manager.requests[0]
    assert request.url().toString() == updates.LATEST_API_URL
    assert not request.hasRawHeader('Authorization') and not request.hasRawHeader('Cookie')
    assert request.attribute(QNetworkRequest.Attribute.RedirectPolicyAttribute) == QNetworkRequest.RedirectPolicy.ManualRedirectPolicy
    assert request.attribute(QNetworkRequest.Attribute.CookieLoadControlAttribute) == QNetworkRequest.LoadControl.Manual
    assert request.attribute(QNetworkRequest.Attribute.CookieSaveControlAttribute) == QNetworkRequest.LoadControl.Manual
    assert reply.buffer_limit == updates.MAX_RESPONSE_BYTES + 1
    reply.feed(payload())
    assert not checker.busy and not checker.timer.isActive() and not bad
    assert [release.version for release in good] == ['1.0.3']


@pytest.mark.parametrize('status', [301, 302, 403, 404, 429, 500, None])
def test_http_failures_never_report_an_up_to_date_installation(app, status):
    checker, good, bad = checker_for(Reply(status=status))
    checker.start()
    checker.reply.feed(payload())
    assert not good and len(bad) == 1 and not checker.busy


def test_tls_failure_is_not_ignored_even_with_a_response(app):
    checker, good, bad = checker_for(Reply(error=QNetworkReply.NetworkError.SslHandshakeFailedError))
    checker.start()
    checker.reply.feed(payload())
    assert not good and bad == [updates.NETWORK_ERROR]


def test_timeout_aborts_and_late_response_is_ignored(app):
    reply = Reply()
    checker, good, bad = checker_for(reply)
    checker.start()
    checker._timeout()
    reply.feed(payload())
    assert reply.aborted and not checker.busy and not good and len(bad) == 1


def test_oversized_stream_is_aborted_once_without_recursion(app):
    reply = Reply()
    checker, good, bad = checker_for(reply)
    checker.start()
    reply.feed(b'x' * updates.MAX_RESPONSE_BYTES, finish=False)
    reply.feed(b'xx', finish=False)
    assert reply.aborted and not checker.busy and not good and bad == [updates.INVALID_RESPONSE]
    assert not checker.body


def test_cancel_does_not_emit_result_and_allows_retry(app):
    reply = Reply()
    checker, good, bad = checker_for(reply)
    checker.start()
    checker.cancel()
    reply.feed(payload())
    assert reply.aborted and not checker.timer.isActive() and not good and not bad
    next_reply = Reply()
    checker.manager.reply = next_reply
    checker.start()
    next_reply.feed(payload(release_data('1.0.4')))
    assert [release.version for release in good] == ['1.0.4'] and not bad


class Preparer(QObject):
    prepared = Signal()
    failed = Signal(str)
    progress = Signal(int)

    def __init__(self):
        super().__init__()
        self.package = None

    @property
    def busy(self):
        return self.package is not None

    def start(self, package):
        assert not self.busy
        self.package = package

    def cancel(self):
        self.package = None


def test_startup_offer_later_manual_reopen_download_and_restart(app, monkeypatch, tmp_path):
    from director_control import update_ui
    checker, _, _ = checker_for(Reply())
    prep = Preparer()
    panel = update_ui.UpdatePanel(checker=checker, preparer=prep, installed_version='1.0.2', supported=True)
    restarts, notices, hints = [], [], []
    panel.restart_requested.connect(lambda: restarts.append(True))
    panel.update_ready.connect(notices.append)
    panel.indicator_changed.connect(hints.append)
    monkeypatch.setattr(update_ui, 'pending_target', lambda *args: None)
    panel.start_automatic()
    assert panel.startup.isActive() and panel.daily.isActive()
    panel._auto_check()
    data = release_data()
    data['body'] = '# v1.0.3\n\nEnglish notes.\n\n## Что нового\n\n- Итоги недели\n\nSource commit: xyz'
    checker.reply.feed(payload(data))
    assert panel.dialog.isVisible() and not prep.busy and not restarts
    assert '1.0.3' in panel.dialog.title.text() and hints[-1]
    assert '1.0.2' in panel.dialog.metadata.text()
    assert not panel.dialog.progress.isVisible()
    assert panel.dialog.description.toPlainText() == '• Итоги недели'
    QTest.keyClick(panel.dialog, Qt.Key.Key_Return)
    assert not panel.dialog.isVisible() and not prep.busy
    checker.manager.reply = Reply()
    panel._auto_check()
    checker.reply.feed(payload(data))
    assert not panel.dialog.isVisible() and not prep.busy
    checker.manager.reply = Reply()
    panel.check_button.click()
    checker.reply.feed(payload(data))
    assert panel.dialog.isVisible()
    panel.dialog.confirm.click()
    assert not panel.dialog.isVisible() and prep.package == panel.release.package
    assert not restarts and not notices and not panel.progress.isHidden()
    prep.progress.emit(38)
    assert panel.progress.value() == 38
    panel.show_details()
    assert panel.dialog.confirm.isHidden() and panel.dialog.progress.isVisible()
    assert panel.dialog.progress.value() == 38
    prep.progress.emit(63)
    assert panel.dialog.progress.value() == 63
    panel.dialog.later.click()
    target = tmp_path / 'v1.0.3' / 'DirectorCalendar.exe'
    monkeypatch.setattr(update_ui, 'pending_target', lambda *args: target)
    prep.package = None
    prep.prepared.emit()
    assert notices == ['1.0.3'] and not restarts and not panel.dialog.isVisible()
    panel.details_button.click()
    assert panel.dialog.confirm.text() == 'Перезапустить и установить'
    assert not panel.dialog.progress.isVisible()
    QTest.keyClick(panel.dialog, Qt.Key.Key_Escape)
    assert not panel.dialog.isVisible() and not restarts
    panel.show_details()
    panel.dialog.confirm.click()
    assert restarts == [True]
    panel.cancel()
    panel.close()


def test_announcement_formats_highlights_and_keeps_html_in_notes_literal(app):
    from director_control.update_ui import UpdatePanel
    checker, _, _ = checker_for(Reply())
    panel = UpdatePanel(checker=checker, preparer=Preparer(), installed_version='1.0.2', supported=True)
    data = release_data()
    data['body'] = ('# v1.0.3\n\nEnglish notes\n\n## Что нового\n\n'
                    '- Нажми **«Требуют проверки»** рядом с результатом обновления.\n'
                    '- Для заметки используй <b>текст</b>.\n\nSource commit: example')
    try:
        panel.check_button.click()
        checker.reply.feed(payload(data))
        notes = panel.dialog.description
        assert notes.isReadOnly() and notes.accessibleName()
        text = notes.toPlainText()
        assert 'Нажми «Требуют проверки»' in text and '<b>текст</b>' in text
        assert '**' not in text and 'English notes' not in text and 'Source commit:' not in text
        highlight = notes.document().find('«Требуют проверки»')
        assert not highlight.isNull() and highlight.charFormat().fontWeight() >= QFont.Weight.DemiBold
    finally:
        panel.cancel()
        panel.close()


def test_disabled_auto_checks_and_manual_retry(app, tmp_path, monkeypatch):
    from director_control import update_ui
    from director_control.storage import Store
    store = Store(tmp_path / 'preferences.db')
    store.set_setting('app_auto_updates', '0')
    checker, _, _ = checker_for(Reply())
    prep = Preparer()
    panel = update_ui.UpdatePanel(store=store, checker=checker, preparer=prep, installed_version='1.0.2', supported=True)
    monkeypatch.setattr(update_ui, 'pending_target', lambda *args: None)
    panel.show()
    panel.start_automatic()
    assert not panel.automatic.isChecked() and not panel.startup.isActive() and not panel.daily.isActive()
    panel._auto_check()
    assert not checker.manager.requests
    panel.check_button.click()
    checker.reply.feed(payload())
    assert panel.dialog.isVisible() and not prep.busy
    panel.dialog.confirm.click()
    assert prep.busy
    panel.cancel_button.click()
    assert not prep.busy and panel.ready_version is None and panel.progress.isHidden()
    panel.details_button.click()
    assert panel.dialog.confirm.text() == 'Повторить загрузку'
    panel.dialog.confirm.click()
    assert prep.busy
    prep.cancel()
    error = 'Загрузка прервалась. Проверь подключение и попробуй снова.'
    prep.failed.emit(error)
    assert panel.dialog.isVisible() and panel.dialog.state.text() == error
    assert not panel.dialog.progress.isVisible() and panel.dialog.confirm.text() == 'Повторить загрузку'
    QTest.keyClick(panel.dialog, Qt.Key.Key_Return)
    assert not prep.busy and not panel.dialog.isVisible()
    panel.automatic.setChecked(True)
    assert panel.daily.isActive() and store.get_setting('app_auto_updates') == '1'
    panel.cancel()
    assert not prep.busy
    panel.close()


def test_pending_update_can_be_reopened_offline_after_ordinary_close(app, tmp_path, monkeypatch):
    from director_control import update_ui
    target = tmp_path / 'v1.0.3' / 'DirectorCalendar.exe'
    notes = target.parent / '_internal/director_control/release-notes.md'
    notes.parent.mkdir(parents=True)
    notes.write_text('# v1.0.3\n\n## Что нового\n\nЗаметки', encoding='utf-8')
    monkeypatch.setattr(update_ui, 'pending_target', lambda *args: target)
    checker, _, _ = checker_for(Reply(status=500))
    panel = update_ui.UpdatePanel(checker=checker, preparer=Preparer(), installed_version='1.0.2', supported=True)
    panel.start_automatic()
    assert panel.dialog.isVisible()
    panel.dialog.reject()
    panel._auto_check()
    checker.reply.feed(b'')
    assert panel.ready_version == '1.0.3' and not panel.dialog.isVisible()
    panel.details_button.click()
    assert panel.dialog.description.toPlainText() == 'Заметки'
    assert panel.dialog.confirm.text() == 'Перезапустить и установить'
    panel.cancel()
    panel.close()


def test_requested_restart_waits_for_sync_backup_and_open_form(app, tmp_path, monkeypatch):
    from director_control import package_update
    from PySide6.QtWidgets import QDialog
    from director_control.storage import Store
    from director_control.ui import MainWindow
    window = MainWindow(Store(tmp_path / 'restart.db'))
    window.update_panel.ready_version = '2.0.0'
    confirmations = []
    monkeypatch.setattr(package_update, 'activate_package', lambda exe, current, version: confirmations.append(version))
    closed = []
    monkeypatch.setattr(window, 'close', lambda: closed.append(True) or True)
    with monkeypatch.context() as patch:
        patch.setattr(type(window.mail_panel), 'busy', property(lambda _: True))
        window._restart_for_update()
    with monkeypatch.context() as patch:
        patch.setattr(type(window.backup_panel), 'busy', property(lambda _: True))
        window._restart_for_update()
    dialog = QDialog(window)
    dialog.setModal(True)
    dialog.show()
    app.processEvents()
    window._restart_for_update()
    dialog.reject()
    assert not closed and not confirmations and not getattr(window, 'restart_after_close', False)
    window._restart_for_update()
    assert confirmations == ['2.0.0'] and closed == [True] and window.restart_after_close
    window.deleteLater()
    from PySide6.QtCore import QEvent
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_home_indicator_reopens_notes_and_ready_notice_requires_a_click(app, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QPushButton
    from director_control import update_ui, package_update
    from director_control.storage import Store
    from director_control.ui import MainWindow
    monkeypatch.setattr(update_ui, 'packaged', lambda: True)
    monkeypatch.setattr(update_ui, 'pending_target', lambda *a: None)
    window = MainWindow(Store(tmp_path / 'home.db'))
    window.show()
    app.processEvents()
    panel = window.update_panel
    assert window.tabs.currentIndex() == 0 and window.update_indicator.isHidden()
    panel.checker._manager = Manager(Reply())
    panel._auto_check()
    panel.checker.reply.feed(payload(release_data('5.0.0')))
    assert panel.dialog.isVisible() and window.update_indicator.isVisible()
    panel.dialog.later.click()
    window.update_indicator.click()
    assert panel.dialog.isVisible() and '5.0.0' in panel.dialog.title.text()
    panel.dialog.reject()
    monkeypatch.setattr(update_ui, 'pending_target', lambda *a: tmp_path / 'v5.0.0' / 'DirectorCalendar.exe')
    panel._prepared()
    app.processEvents()
    assert window.update_notice.isVisible() and window.isVisible()
    buttons = {b.text(): b for b in window.update_notice.findChildren(QPushButton)}
    buttons['Позже'].click()
    assert window.update_notice.isHidden() and window.update_indicator.isVisible()
    requests = []
    monkeypatch.setattr(package_update, 'activate_package', lambda exe, current, version: requests.append(version))
    assert not requests
    panel._notify_ready()
    buttons['Перезапустить'].click()
    assert requests == ['5.0.0'] and window.restart_after_close and not window.isVisible()
    window.deleteLater()
    from PySide6.QtCore import QEvent
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.mark.parametrize('installed, expected', [('1.0.3', 'последняя опубликованная'), ('1.0.4', 'новее')])
def test_same_or_older_release_never_offers_downgrade(app, installed, expected):
    from director_control.update_ui import UpdatePanel
    reply = Reply()
    checker, _, _ = checker_for(reply)
    panel = UpdatePanel(checker=checker, installed_version=installed)
    panel.check_button.click()
    reply.feed(payload())
    assert expected in panel.status.text() and panel.details_button.isHidden() and panel.dialog is None
    panel.close()


def test_failed_recheck_keeps_previous_offer_accessible(app):
    from director_control.update_ui import UpdatePanel
    checker, _, _ = checker_for(Reply())
    panel = UpdatePanel(checker=checker, installed_version='1.0.2')
    panel.check_button.click()
    checker.reply.feed(payload())
    panel.dialog.reject()
    checker.manager.reply = Reply(status=500)
    panel.check_button.click()
    checker.reply.feed(b'private server detail')
    assert panel.offered_version == '1.0.3' and not panel.details_button.isHidden()
    assert not panel.dialog.isVisible() and 'private' not in panel.status.text() and panel.check_button.isEnabled()
    panel.close()


def test_main_window_close_cancels_pending_check_without_wait(app, tmp_path, monkeypatch):
    from director_control.storage import Store
    from director_control.ui import MainWindow
    window = MainWindow(Store(tmp_path / 'update-check.db'))
    reply = Reply()
    window.update_panel.checker._manager = Manager(reply)
    window.update_panel.check_button.click()
    assert window.update_panel.checker.busy
    assert window.close()
    assert reply.aborted and not window.update_panel.checker.busy
