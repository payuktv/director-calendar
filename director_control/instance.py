"""Own the database before initialization and activate an existing app on relaunch."""
import hashlib
import os
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QLockFile, QObject, QTimer, Signal

from .i18n import tr


class SingleInstance(QObject):
    activated = Signal()

    def __init__(self, database):
        super().__init__()
        database = Path(database).resolve()
        database.parent.mkdir(parents=True, exist_ok=True)
        identity = os.path.normcase(str(database))
        self.name = 'DirectorCalendar-' + hashlib.sha256(identity.encode()).hexdigest()[:24]
        self.lock = QLockFile(str(database.parent / (self.name + '.lock')))
        self.lock.setStaleLockTime(0)
        self.activation_path = database.parent / (self.name + '.activate')
        self._last_activation = ''
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self._poll)
        self.owner = False

    def acquire(self):
        if not self.lock.tryLock(0):
            if self.lock.error() != QLockFile.LockError.LockFailedError:
                raise OSError(tr('Не удалось получить доступ к папке данных приложения.'))
            return False
        self.owner = True
        self.activation_path.unlink(missing_ok=True)
        self.timer.start()
        return True

    def notify(self):
        temporary = self.activation_path.with_suffix('.wake-' + uuid4().hex)
        try:
            temporary.write_text(uuid4().hex, encoding='ascii')
            os.replace(temporary, self.activation_path)
            return True
        except OSError:
            return False
        finally:
            temporary.unlink(missing_ok=True)

    def _poll(self):
        if not self.owner:
            return
        try:
            token = self.activation_path.read_text(encoding='ascii')
        except (OSError, UnicodeError):
            return
        if token and token != self._last_activation:
            self._last_activation = token
            self.activated.emit()

    def close(self):
        if self.owner:
            self.timer.stop()
            try:
                self.activation_path.unlink(missing_ok=True)
            except OSError:
                pass
            finally:
                self.lock.unlock()
                self.owner = False
