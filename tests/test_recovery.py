from pathlib import Path
import pytest
from director_control.storage import Store
from director_control.backups import create_backup
from director_control.recovery import recover_database
from director_control.updates import prepare_version_update


def test_corrupt_database_recovers_and_opens(tmp_path):
    store = Store(tmp_path / 'live.db')
    store.set_setting('test_value', 'preserved')
    copy = create_backup(store)
    store.path.write_bytes(b'broken')
    archive = recover_database(store.path, copy)
    assert (archive / 'live.db').read_bytes() == b'broken'
    prepare_version_update(store.path)
    assert Store(store.path).get_setting('test_value') == 'preserved'


def test_invalid_copy_keeps_original(tmp_path):
    path = tmp_path / 'live.db'
    path.write_bytes(b'original')
    bad = tmp_path / 'bad.db'
    bad.write_bytes(b'bad')
    with pytest.raises(ValueError):
        recover_database(path, bad)
    assert path.read_bytes() == b'original'


def test_failed_swap_keeps_original_and_sidecars(tmp_path, monkeypatch):
    from director_control import recovery
    copy = create_backup(Store(tmp_path / 'source.db'))
    path = tmp_path / 'live.db'
    path.write_bytes(b'broken')
    wal = Path(str(path) + '-wal')
    wal.write_bytes(b'wal')
    replace = recovery.os.replace
    def fail(src, dst):
        if Path(dst) == path:
            raise OSError('test failure')
        return replace(src, dst)
    monkeypatch.setattr(recovery.os, 'replace', fail)
    with pytest.raises(OSError):
        recover_database(path, copy)
    assert path.read_bytes() == b'broken'
    assert wal.read_bytes() == b'wal'


def test_newer_copy_is_rejected(tmp_path):
    store = Store(tmp_path / 'future.db')
    store.set_setting('app_last_version', '99.0.0')
    source = create_backup(store)
    target = tmp_path / 'live.db'
    target.write_bytes(b'original')
    with pytest.raises(ValueError, match='новой'):
        recover_database(target, source)
    assert target.read_bytes() == b'original'


def test_cancel_recovery_dialog_preserves_original(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox
    from director_control.recovery import offer_recovery
    app = QApplication.instance() or QApplication([])
    target = tmp_path / 'live.db'
    target.write_bytes(b'original')
    monkeypatch.setattr(QMessageBox, 'question', lambda *a: QMessageBox.StandardButton.No)
    assert not offer_recovery(target, ValueError('broken'))
    assert target.read_bytes() == b'original'
    assert app is not None
