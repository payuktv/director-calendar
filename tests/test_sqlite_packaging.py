"""The native SQLite pin must be verified before it can enter a release."""
import hashlib
import io
import json
from pathlib import Path
import zipfile

import pytest

from scripts import prepare_sqlite, release
from tests.test_release import bundle, SHA, VERSION


def test_changed_download_is_rejected_before_extraction():
    with pytest.raises(ValueError, match='checksum'):
        prepare_sqlite.extract_dll(b'an untrusted download')


@pytest.mark.parametrize('names', [['../sqlite3.dll'], ['sqlite3.dll', 'sqlite3.dll'], ['readme.txt']])
def test_archive_needs_one_exact_dll_member(monkeypatch, names):
    data = io.BytesIO()
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', UserWarning)
        with zipfile.ZipFile(data, 'w') as archive:
            for name in names:
                archive.writestr(name, b'synthetic DLL')
    raw = data.getvalue()
    monkeypatch.setattr(prepare_sqlite, 'ARCHIVE_SHA3', hashlib.sha3_256(raw).hexdigest())
    with pytest.raises(ValueError, match='archive'):
        prepare_sqlite.extract_dll(raw)


def test_release_rejects_old_runtime_even_when_other_checks_pass(tmp_path):
    folder = bundle(tmp_path)
    report_path = folder / 'distribution-check.json'
    report = json.loads(report_path.read_text())
    report['sqlite_version'] = '3.50.4'
    report_path.write_text(json.dumps(report))
    with pytest.raises(ValueError, match='SQLite'):
        release.verify_bundle(folder, VERSION, SHA)


@pytest.mark.parametrize('missing', ['untrusted_backup_rejected', 'obsolete_files_removed',
                                    'installed_file_manifest', 'reparse_path_rejected',
                                    'backup_settings_validated', 'backup_destination_local'])
def test_release_requires_new_security_and_upgrade_checks(tmp_path, missing):
    folder = bundle(tmp_path)
    report_path = folder / 'distribution-check.json'
    report = json.loads(report_path.read_text())
    report.pop(missing)
    report_path.write_text(json.dumps(report))
    with pytest.raises(ValueError, match='acceptance'):
        release.verify_bundle(folder, VERSION, SHA)


def test_retired_file_list_is_explicit_and_only_covers_program_files():
    import re
    path = Path(__file__).resolve().parents[1] / 'packaging/retired-files.iss'
    entries = [line for line in path.read_text().splitlines() if line.startswith('Type:')]
    assert entries
    paths = []
    for line in entries:
        match = re.fullmatch(r'Type: files; Name: "\{app\}\\(_internal\\[^"*?]+)"; Check: RetiredFileIsSafe\(\'([^\']+)\'\)', line)
        assert match and match[1] == match[2]
        assert all(part not in ('', '.', '..') and ':' not in part for part in match[1].split('\\'))
        paths.append(match[1].lower())
    assert len(paths) == len(set(paths))
