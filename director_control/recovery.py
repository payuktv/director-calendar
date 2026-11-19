"""Offline recovery; caller must hold the application's database lock."""
from pathlib import Path
import os
import shutil
import tempfile
from uuid import uuid4

from .i18n import tr
from .backups import validate_compatible_database, _copy_database, _cleanup_temporary, _restore_backup_settings
from .diagnostics import record_error


def recover_database(database, source):
    from .storage import Store
    database, source = Path(database).resolve(), Path(source).resolve()
    if source == database:
        raise ValueError(tr('Выбери резервную копию, а не рабочую базу.'))
    validate_compatible_database(source)
    descriptor, name = tempfile.mkstemp(prefix='.recovery-', suffix='.db', dir=database.parent)
    os.close(descriptor)
    staged = Path(name)
    moved = []
    try:
        _copy_database(source, staged)
        validate_compatible_database(staged)
        store = Store(staged)
        with store._connect() as con:
            _restore_backup_settings(con)
            store._audit(con, None, tr('База данных'), tr('Восстановление из копии'),
                         {tr('копия'): source.name})
        validate_compatible_database(staged)
        archive = database.parent / 'recovery' / uuid4().hex
        archive.mkdir(parents=True)
        # Preserve exact bytes even when SQLite cannot read the damaged database.
        originals = [Path(str(database) + suffix) for suffix in ('', '-wal', '-shm', '-journal')]
        for path in originals:
            if path.exists():
                shutil.copy2(path, archive / path.name)
        try:
            for path in originals[1:]:
                if path.exists():
                    saved = archive / (path.name + '.held')
                    os.replace(path, saved)
                    moved.append((saved, path))
            os.replace(staged, database)
        except Exception:
            for saved, path in reversed(moved):
                os.replace(saved, path)
            raise
        return archive
    finally:
        _cleanup_temporary(staged)


def offer_recovery(database, error):
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    answer = QMessageBox.question(None, tr('Не удалось открыть базу'),
        tr('Рабочая база недоступна или не прошла проверку.\n') + str(error) +
        tr('\n\nВосстановить из резервной копии? Исходные файлы будут сохранены отдельно.'),
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No)
    if answer != QMessageBox.StandardButton.Yes:
        return False
    source, _ = QFileDialog.getOpenFileName(None, tr('Выбрать исправную копию'),
        str(Path(database).parent / 'backups'), tr('База данных (*.db *.sqlite)'))
    if not source:
        return False
    answer = QMessageBox.question(None, tr('Подтвердить восстановление'),
        tr('Рабочие события, история и настройки будут заменены выбранной копией. '
        'Автоматические копии будут сохраняться ежедневно в стандартную папку рядом с базой; хранится 30 копий. '
        'Другую папку можно выбрать в настройках после восстановления. Продолжить?'),
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No)
    if answer != QMessageBox.StandardButton.Yes:
        return False
    try:
        archive = recover_database(database, source)
    except Exception as exc:
        record_error('recovery.restore', exc)
        QMessageBox.warning(None, tr('Восстановление не выполнено'), str(exc))
        return False
    QMessageBox.information(None, tr('База восстановлена'),
        tr('Открой приложение снова. Исходные файлы сохранены:\n') + str(archive))
    return True
