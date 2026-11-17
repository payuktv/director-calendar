import copy
import json
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QNetworkReply, QNetworkRequest
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
            'assets': [{'name': f'DirectorCalendar-{version}-Setup-x64.exe', 'state': 'uploaded',
                        'size': 120000000,
                        'browser_download_url': f'{root}/releases/download/v{version}/DirectorCalendar-{version}-Setup-x64.exe'}]}


def payload(data=None):
    return json.dumps(release_data() if data is None else data).encode()


def test_numeric_versions_and_installer_are_preserved():
    release = updates.parse_release(payload(release_data('1.10.0')))
    assert updates.version_key(release.version) > updates.version_key('1.9.9')
    assert release.installer_url.endswith('/v1.10.0/DirectorCalendar-1.10.0-Setup-x64.exe')


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


@pytest.mark.parametrize('patch', [{'size': 0}, {'size': True}, {'state': 'new'}])
def test_unfinished_assets_are_rejected(patch):
    data = release_data()
    data['assets'][0].update(patch)
    with pytest.raises(ValueError):
        updates.parse_release(payload(data))


def test_ambiguous_installer_is_rejected():
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


def test_update_panel_displays_result_and_opens_only_requested_link(app, monkeypatch):
    from director_control import update_ui
    reply = Reply()
    checker, good, bad = checker_for(reply)
    panel = update_ui.UpdatePanel(checker=checker, installed_version='1.0.2')
    opened = []
    monkeypatch.setattr(update_ui.QDesktopServices, 'openUrl', lambda url: opened.append(url.toString()) or True)
    assert not checker.manager.requests
    panel.check_button.click()
    assert not panel.check_button.isEnabled() and panel.download_button.isHidden()
    reply.feed(payload())
    assert not opened and panel.check_button.isEnabled()
    assert '1.0.3' in panel.status.text() and not panel.download_button.isHidden()
    panel.download_button.click()
    panel.notes_button.click()
    assert opened == [good[0].installer_url, good[0].page_url]
    panel.close()


@pytest.mark.parametrize('installed, expected', [('1.0.3', 'последняя опубликованная'), ('1.0.4', 'новее')])
def test_same_or_older_release_never_offers_downgrade(app, installed, expected):
    from director_control.update_ui import UpdatePanel
    reply = Reply()
    checker, _, _ = checker_for(reply)
    panel = UpdatePanel(checker=checker, installed_version=installed)
    panel.check_button.click()
    reply.feed(payload())
    assert expected in panel.status.text() and panel.download_button.isHidden()
    panel.close()


def test_failed_recheck_clears_previous_offer(app):
    from director_control.update_ui import UpdatePanel
    checker, _, _ = checker_for(Reply())
    panel = UpdatePanel(checker=checker, installed_version='1.0.2')
    panel.check_button.click()
    checker.reply.feed(payload())
    checker.manager.reply = Reply(status=500)
    panel.check_button.click()
    assert panel.release is None and panel.download_button.isHidden()
    checker.reply.feed(b'private server detail')
    assert panel.release is None and 'private' not in panel.status.text() and panel.check_button.isEnabled()
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
