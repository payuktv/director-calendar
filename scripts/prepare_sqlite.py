"""Fetch the pinned upstream x64 SQLite DLL; never modify the system Python.

The archive's SHA3-256 is published at https://www.sqlite.org/download.html.
PyInstaller replaces its collected DLL with this verified file. A private copy
of CPython's extension also lets Windows CI test the same SQLite via PYTHONPATH.
"""
import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
from urllib.request import urlopen
import zipfile

VERSION = '3.54.1'
SOURCE_ID = '2026-10-16 14:45:20 555e07ef33f69a0957d24d8e555b702464a131d6f1607f4c3c1e4551e8e6ca76'
URL = 'https://www.sqlite.org/2026/sqlite-dll-win-x64-3540100.zip'
ARCHIVE_SHA3 = 'c2d09c8babb9399277055c057c97a53f1ffd7c5f11d0c1f2118ffdfa39f2daa4'
MAX_DOWNLOAD = 8 * 1024 * 1024


def extract_dll(data):
    if len(data) > MAX_DOWNLOAD or hashlib.sha3_256(data).hexdigest() != ARCHIVE_SHA3:
        raise ValueError('SQLite upstream archive checksum mismatch')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = [item for item in archive.infolist() if item.filename == 'sqlite3.dll']
        if len(entries) != 1 or entries[0].file_size > MAX_DOWNLOAD:
            raise ValueError('Unexpected SQLite upstream archive')
        return archive.read(entries[0])


def prepare(folder):
    if sys.platform != 'win32' or struct.calcsize('P') != 8:
        raise ValueError('SQLite overlay requires Windows x64 Python')
    folder = folder.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    # Hash both fresh downloads and cached archives on every build.
    archive = folder / 'upstream.zip'
    if archive.is_file():
        data = archive.read_bytes()
    else:
        with urlopen(URL, timeout=30) as response:
            if response.url != URL:
                raise ValueError('Unexpected SQLite download redirect')
            data = response.read(MAX_DOWNLOAD + 1)
    dll = extract_dll(data)
    (folder / 'sqlite3.dll').write_bytes(dll)
    archive.write_bytes(data)
    extension = Path(importlib.util.find_spec('_sqlite3').origin)
    target = folder / extension.name
    if extension.resolve() != target.resolve():
        shutil.copyfile(extension, target)
    # A new process imports the extension beside the DLL, not the system DLL.
    code = "import sqlite3,json; c=sqlite3.connect(':memory:'); print(json.dumps([sqlite3.sqlite_version,c.execute('select sqlite_source_id()').fetchone()[0]]))"
    actual = json.loads(subprocess.check_output([sys.executable, '-c', code], cwd=folder, text=True, timeout=15))
    if actual != [VERSION, SOURCE_ID]:
        raise ValueError('The Python extension did not load the pinned SQLite DLL')
    info = {'version': VERSION, 'source_id': SOURCE_ID, 'url': URL,
            'archive_sha3_256': ARCHIVE_SHA3, 'dll_sha256': hashlib.sha256(dll).hexdigest()}
    (folder / 'sqlite-build.json').write_text(json.dumps(info, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(info))
    return folder / 'sqlite3.dll'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    prepare(parser.parse_args().folder)
