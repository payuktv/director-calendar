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
    ('openssl_version', [3, 5, 8]), ('openssl_version', None),
])
def test_publication_rejects_wrong_native_runtime(tmp_path, field, value):
    folder = bundle(tmp_path)
    path = folder / 'distribution-check.json'
    report = json.loads(path.read_text())
    report[field] = value
    path.write_text(json.dumps(report))
    with pytest.raises(ValueError, match='pinned runtime'):
        release.verify_bundle(folder, VERSION, SHA)


def test_missing_runtime_acceptance_is_not_publishable(tmp_path):
    folder = bundle(tmp_path)
    path = folder / 'distribution-check.json'
    report = json.loads(path.read_text())
    report.pop('runtime_patched')
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
    assert report['openssl_version'] == list(ssl.OPENSSL_VERSION_INFO[:3])
