"""Reject an old/incorrect native runtime even when other release checks pass."""
import json
from pathlib import Path

import pytest

from director_control.runtime_versions import PYTHON_VERSION, runtime_versions
from scripts import release
from tests.test_release import bundle, SHA, VERSION


@pytest.mark.parametrize('field,value', [
    ('python_version', '3.13.17'), ('python_version', '3.14.9'),
    ('python_version', None), ('python_implementation', 'PyPy'),
    ('python_bits', 32), ('python_free_threaded', True),
    ('python_free_threaded', 0), ('expat_version', 'expat_2.8.5'),
    ('expat_version', 'expat_2.9.0'), ('elementtree_version', 'Expat 2.9.0'),
    ('elementtree_accelerated', False), ('elementtree_accelerated', 1),
    ('openssl_version', 'OpenSSL 3.5.8 1 Jul 2026'), ('openssl_version', None),
])
def test_publication_rejects_wrong_native_runtime(tmp_path, field, value):
    folder = bundle(tmp_path)
    path = folder / 'distribution-check.json'
    report = json.loads(path.read_text())
    report[field] = value
    path.write_text(json.dumps(report))
    with pytest.raises(ValueError, match='pinned runtime'):
        release.verify_bundle(folder, VERSION, SHA)


@pytest.mark.parametrize('field', ['runtime_patched', 'xml_runtime_verified', 'backup_records_validated'])
def test_missing_runtime_acceptance_is_not_publishable(tmp_path, field):
    folder = bundle(tmp_path)
    path = folder / 'distribution-check.json'
    report = json.loads(path.read_text())
    report.pop(field)
    path.write_text(json.dumps(report))
    with pytest.raises(ValueError, match='acceptance'):
        release.verify_bundle(folder, VERSION, SHA)


def test_ci_and_executable_runtime_policy_agree():
    root = Path(__file__).resolve().parents[1]
    assert (root / '.python-version').read_text().strip() == PYTHON_VERSION


def test_runtime_report_is_json_serializable_and_reads_actual_interpreter():
    import platform
    import pyexpat
    import ssl
    report = json.loads(json.dumps(runtime_versions()))
    assert report['python_version'] == platform.python_version()
    assert report['expat_version'] == pyexpat.EXPAT_VERSION
    assert report['openssl_version'] == ssl.OPENSSL_VERSION


def test_openssl_3_patch_number_is_preserved(monkeypatch):
    import ssl
    monkeypatch.setattr(ssl, 'OPENSSL_VERSION_INFO', (3, 5, 0, 9, 0))
    monkeypatch.setattr(ssl, 'OPENSSL_VERSION', 'OpenSSL 3.5.9 29 Sep 2026')
    assert runtime_versions()['openssl_version'] == 'OpenSSL 3.5.9 29 Sep 2026'
