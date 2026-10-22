import sys
from types import SimpleNamespace

import pytest

from director_control.credentials import Credentials
from director_control.mail_calendar import CalendarError


def test_windows_uses_explicit_vault_and_can_forget(monkeypatch):
    saved = {}
    class Vault:
        def get_password(self, service, key): return saved.get((service, key))
        def set_password(self, service, key, value): saved[service, key] = value
        def delete_password(self, service, key): del saved[service, key]
    monkeypatch.setattr(Credentials, "can_remember", property(lambda self: True))
    monkeypatch.setitem(sys.modules, "keyring.backends.Windows", SimpleNamespace(WinVaultKeyring=Vault))
    first = Credentials()
    first.set("account-key", "test-only-secret", True)
    assert Credentials().get("account-key") == "test-only-secret"
    first.set("account-key", "test-only-secret", False)
    assert first.get("account-key") == "test-only-secret"
    assert Credentials().get("account-key") == ""
    assert saved == {}


def test_vault_failure_never_falls_back_to_plaintext_or_echoes_exception(monkeypatch):
    class Vault:
        def set_password(self, *args): raise RuntimeError("test-only-secret")
    monkeypatch.setattr(Credentials, "can_remember", property(lambda self: True))
    monkeypatch.setitem(sys.modules, "keyring.backends.Windows", SimpleNamespace(WinVaultKeyring=Vault))
    credentials = Credentials()
    with pytest.raises(CalendarError) as exc:
        credentials.set("account-key", "test-only-secret", True)
    assert "test-only-secret" not in str(exc.value)
    assert credentials._session == {}


def test_non_windows_session_does_not_persist(monkeypatch):
    monkeypatch.setattr(Credentials, "can_remember", property(lambda self: False))
    first = Credentials()
    first.set("account-key", "test-only-secret", False)
    assert first.get("account-key") == "test-only-secret"
    assert Credentials().get("account-key") == ""
