"""Source provenance, extraction safety and actual paired XML extension checks."""
import hashlib
import io
from pathlib import Path
import tarfile

import pytest

from scripts import prepare_expat
from director_control.runtime_versions import EXPAT_VERSION, verify_xml_runtime


def archive(name, kind=tarfile.REGTYPE, data=b'source'):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w:xz') as tar:
        item = tarfile.TarInfo(name)
        item.type = kind
        if kind == tarfile.REGTYPE:
            item.size = len(data)
        else:
            item.linkname = '../../outside'
        tar.addfile(item, io.BytesIO(data) if item.size else None)
    return output.getvalue()


def test_changed_or_oversized_source_download_is_rejected(monkeypatch):
    digest = hashlib.sha256(b'expected').hexdigest()
    assert prepare_expat.verified_bytes(b'expected', digest) == b'expected'
    with pytest.raises(ValueError, match='checksum'):
        prepare_expat.verified_bytes(b'changed', digest)
    monkeypatch.setattr(prepare_expat, 'MAX_DOWNLOAD', 3)
    with pytest.raises(ValueError, match='checksum'):
        prepare_expat.verified_bytes(b'expected', digest)


@pytest.mark.parametrize('name,kind', [
    ('Python-3.14.10/../outside', tarfile.REGTYPE),
    ('/absolute', tarfile.REGTYPE), ('Python-3.14.10/Lib/evil\\path', tarfile.REGTYPE),
    ('Python-3.14.10/Lib/C:/outside', tarfile.REGTYPE),
    ('other/Lib/module.py', tarfile.REGTYPE),
    ('Python-3.14.10/Lib/link.py', tarfile.SYMTYPE),
    ('Python-3.14.10/Lib/link.py', tarfile.LNKTYPE),
])
def test_archive_paths_and_links_cannot_escape_staging(tmp_path, name, kind):
    with pytest.raises(ValueError, match='archive'):
        prepare_expat.extract_sources(archive(name, kind), tmp_path / 'staging', 'Python-3.14.10')
    assert not (tmp_path / 'outside').exists()


def test_source_extraction_limits_expanded_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr(prepare_expat, 'MAX_EXPANDED', 2)
    with pytest.raises(ValueError, match='member'):
        prepare_expat.extract_sources(archive('Python-3.14.10/Lib/test.py'), tmp_path, 'Python-3.14.10')
    assert not list(tmp_path.rglob('*'))


def test_native_overlay_and_publication_use_same_python_expat_policy():
    from director_control.runtime_versions import PYTHON_VERSION
    assert prepare_expat.PYTHON_VERSION == PYTHON_VERSION
    assert 'expat_' + prepare_expat.EXPAT_VERSION == EXPAT_VERSION
    assert (Path(__file__).resolve().parents[1] / '.python-version').read_text().strip() == PYTHON_VERSION


def test_actual_xml_runtime_and_fixed_empty_subparser():
    # CI builds both extensions before running the suite; failure is not skipped.
    verify_xml_runtime()
