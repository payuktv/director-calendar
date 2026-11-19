"""Fetch the stable release and its verified portable package metadata."""
from dataclasses import dataclass
import json

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from .package_update import Package, REPOSITORY_URL, version_key

LATEST_API_URL = 'https://api.github.com/repos/payuktv/director-calendar/releases/latest'
MAX_RESPONSE_BYTES = 256 * 1024
CHECK_TIMEOUT_MS = 15000
NETWORK_ERROR = 'Не удалось проверить обновления. Проверь соединение с интернетом и попробуй снова.'
INVALID_RESPONSE = 'Не удалось проверить обновления: получен некорректный ответ.'


@dataclass(frozen=True)
class Release:
    version: str
    page_url: str
    package: Package
    notes: str


def release_description(body):
    """Extract the user-facing Russian section, falling back to older release notes."""
    lines = body.splitlines() if isinstance(body, str) else []
    notes = []
    russian = False
    for line in lines:
        line = line.strip()
        if line == '## Что нового':
            notes.clear()
            russian = True
        elif line.startswith('Source commit:') or (russian and line.startswith('## ')):
            break
        elif not line.startswith('# v'):
            notes.append('• ' + line[2:] if line.startswith(('- ', '* ')) else line)
    return '\n'.join(notes).strip()[:12000] or 'Описание изменений пока не опубликовано.'


def parse_release(payload):
    if not isinstance(payload, bytes) or len(payload) > MAX_RESPONSE_BYTES:
        raise ValueError('Invalid release response')
    try:
        data = json.loads(payload)
        if not isinstance(data, dict) or data.get('draft') is not False or data.get('prerelease') is not False:
            raise ValueError('Not a stable published release')
        tag = data.get('tag_name')
        if not isinstance(tag, str) or not tag.startswith('v'):
            raise ValueError('Invalid release tag')
        version = tag[1:]
        version_key(version)
        page = f'{REPOSITORY_URL}/releases/tag/{tag}'
        if data.get('html_url') != page or not isinstance(data.get('published_at'), str) or not data['published_at']:
            raise ValueError('Invalid release page')
        assets = data.get('assets')
        if not isinstance(assets, list):
            raise ValueError('Missing update assets')
        matches = [a for a in assets if isinstance(a, dict)
                   and a.get('name') == f'DirectorCalendar-{version}-portable-x64.zip']
        if len(matches) != 1:
            raise ValueError('Missing or ambiguous update package')
        asset = matches[0]
        digest = asset.get('digest')
        if not isinstance(digest, str) or not digest.startswith('sha256:'):
            raise ValueError('Missing SHA-256 digest')
        package = Package(version, asset.get('size'), digest[7:])
        if asset.get('state') != 'uploaded' or asset.get('browser_download_url') != package.url:
            raise ValueError('Invalid update package')
        return Release(version, page, package, release_description(data.get('body')))
    except (UnicodeError, TypeError, KeyError, RecursionError) as exc:
        raise ValueError('Invalid release response') from exc


class UpdateChecker(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    busy_changed = Signal(bool)

    def __init__(self, parent=None, *, manager=None):
        super().__init__(parent)
        self._manager = manager
        self.reply = None
        self.body = bytearray()
        self.abort_message = ''
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._timeout)

    @property
    def busy(self):
        return self.reply is not None

    @property
    def manager(self):
        # Opening or closing the calendar must not initialize a network backend.
        if self._manager is None:
            self._manager = QNetworkAccessManager(self)
        return self._manager

    def start(self):
        if self.busy:
            return
        request = QNetworkRequest(QUrl(LATEST_API_URL))
        request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                             QNetworkRequest.RedirectPolicy.ManualRedirectPolicy)
        request.setAttribute(QNetworkRequest.Attribute.CacheLoadControlAttribute,
                             QNetworkRequest.CacheLoadControl.AlwaysNetwork)
        request.setAttribute(QNetworkRequest.Attribute.CookieLoadControlAttribute,
                             QNetworkRequest.LoadControl.Manual)
        request.setAttribute(QNetworkRequest.Attribute.CookieSaveControlAttribute,
                             QNetworkRequest.LoadControl.Manual)
        request.setRawHeader(b'Accept', b'application/vnd.github+json')
        request.setRawHeader(b'X-GitHub-Api-Version', b'2022-11-28')
        request.setRawHeader(b'User-Agent', b'DirectorCalendar-UpdateCheck')
        self.body.clear()
        self.abort_message = ''
        try:
            reply = self.manager.get(request)
        except Exception:
            self.failed.emit(NETWORK_ERROR)
            return
        self.reply = reply
        reply.setReadBufferSize(MAX_RESPONSE_BYTES + 1)
        reply.readyRead.connect(self._read)
        reply.finished.connect(self._finished)
        self.timer.start(CHECK_TIMEOUT_MS)
        self.busy_changed.emit(True)

    def _read(self, reply=None):
        reply = self.sender() if reply is None else reply
        if reply is not self.reply or self.abort_message:
            return
        remaining = MAX_RESPONSE_BYTES + 1 - len(self.body)
        self.body.extend(bytes(reply.read(remaining)))
        if len(self.body) > MAX_RESPONSE_BYTES:
            self.abort_message = INVALID_RESPONSE
            reply.abort()

    def _timeout(self):
        if self.reply is not None:
            self.abort_message = 'Проверка заняла слишком много времени. Попробуй снова.'
            self.reply.abort()

    def _finished(self):
        reply = self.sender()
        if reply is not self.reply:
            return
        self._read(reply)
        # abort() can emit finished synchronously while consuming oversized data.
        if reply is not self.reply:
            return
        self.reply = None
        self.timer.stop()
        error = self.abort_message
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        result = None
        if not error:
            if status in (403, 429):
                error = 'GitHub временно ограничил проверки. Попробуй позже.'
            elif status == 404:
                error = 'Сведения об обновлениях пока недоступны. Попробуй позже.'
            elif status != 200 or reply.error() != QNetworkReply.NetworkError.NoError:
                error = NETWORK_ERROR
            else:
                try:
                    result = parse_release(bytes(self.body))
                except ValueError:
                    error = INVALID_RESPONSE
        self.body.clear()
        reply.deleteLater()
        self.busy_changed.emit(False)
        if error:
            self.failed.emit(error)
        else:
            self.succeeded.emit(result)

    def cancel(self):
        reply, self.reply = self.reply, None
        self.timer.stop()
        self.body.clear()
        if reply is not None:
            reply.abort()
            reply.deleteLater()
            self.busy_changed.emit(False)
