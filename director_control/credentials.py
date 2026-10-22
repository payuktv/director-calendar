"""Use the Windows Credential Manager explicitly; never fall back to plaintext."""
import os

from .mail_calendar import CalendarError


class Credentials:
    def __init__(self):
        self._session = {}

    @property
    def can_remember(self) -> bool:
        return os.name == "nt"

    def get(self, account_key: str) -> str:
        if account_key in self._session:
            return self._session[account_key]
        if not self.can_remember:
            return ""
        try:
            from keyring.backends.Windows import WinVaultKeyring
            return WinVaultKeyring().get_password("DirectorControl.CalDAV", account_key) or ""
        except Exception:
            raise CalendarError("Не удалось открыть хранилище паролей Windows. Введи пароль заново.") from None

    def set(self, account_key: str, password: str, remember: bool) -> None:
        if self.can_remember:
            try:
                from keyring.backends.Windows import WinVaultKeyring
                backend = WinVaultKeyring()
                if remember:
                    backend.set_password("DirectorControl.CalDAV", account_key, password)
                elif backend.get_password("DirectorControl.CalDAV", account_key) is not None:
                    backend.delete_password("DirectorControl.CalDAV", account_key)
            except Exception:
                raise CalendarError("Не удалось обновить хранилище паролей Windows. Настройки не сохранены.") from None
        self._session[account_key] = password
