# Run only on Windows. The source root can point at the previous revision in CI.
import os
import hashlib
import json
from pathlib import Path
import tomllib
from PyInstaller.utils.hooks import collect_data_files, copy_metadata
from PyInstaller.utils.win32.versioninfo import VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable, StringStruct, VarFileInfo, VarStruct

root = Path(os.environ.get('DIRECTOR_BUILD_ROOT', str(Path(SPECPATH).parent))).resolve()
version = tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
version4 = tuple(int(n) for n in version.split('.')) + (0,)
info = VSVersionInfo(ffi=FixedFileInfo(filevers=version4, prodvers=version4, mask=0x3f, flags=0, OS=0x40004, fileType=1, subtype=0, date=(0, 0)),
    kids=[StringFileInfo([StringTable('040904B0', [StringStruct('FileDescription', 'Director Calendar'),
        StringStruct('FileVersion', version), StringStruct('ProductVersion', version),
        StringStruct('ProductName', 'Director Calendar'), StringStruct('OriginalFilename', 'DirectorCalendar.exe')])]),
        VarFileInfo([VarStruct('Translation', [1033, 1200])])])
datas = [(str(root / 'director_control/assets/director-calendar.ico'), 'director_control/assets')]
for package in ('tzdata', 'certifi'):
    datas += collect_data_files(package)
for package in ('keyring', 'icalendar', 'recurring-ical-events', 'PySide6_Essentials', 'shiboken6', 'requests', 'certifi', 'tzdata'):
    datas += copy_metadata(package)
a = Analysis([str(root / 'main.py')], pathex=[str(root)], datas=datas,
             hiddenimports=['keyring.backends.Windows'], excludes=['tkinter', 'pytest'],
             binaries=[], hookspath=[], runtime_hooks=[])
# Replace the DLL collected from CPython, never ship both old and new copies.
sqlite_dll = Path(os.environ['DIRECTOR_SQLITE_DLL']).resolve()
sqlite_info = json.loads((sqlite_dll.parent / 'sqlite-build.json').read_text(encoding='utf-8'))
assert hashlib.sha256(sqlite_dll.read_bytes()).hexdigest() == sqlite_info['dll_sha256']
assert sum(Path(item[0]).name.lower() == 'sqlite3.dll' for item in a.binaries) == 1
a.binaries = [(name, str(sqlite_dll), kind) if Path(name).name.lower() == 'sqlite3.dll'
              else (name, source, kind) for name, source, kind in a.binaries]
# Both extensions must use the same Expat headers/capsule. Never package a mixed
# pair or fall back to the old static Expat bundled in the system interpreter.
expat_dir = Path(os.environ['DIRECTOR_EXPAT_DIR']).resolve()
expat_info = json.loads((expat_dir / 'expat-build.json').read_text(encoding='utf-8'))
assert expat_info['python'] == '3.14.10' and expat_info['expat'] == '2.10.0'
assert set(expat_info['binaries']) == {'pyexpat.pyd', '_elementtree.pyd'}
for filename, digest in expat_info['binaries'].items():
    assert hashlib.sha256((expat_dir / filename).read_bytes()).hexdigest() == digest
    assert sum(Path(item[0]).name.lower() == filename for item in a.binaries) == 1
a.binaries = [(name, str(expat_dir / Path(name).name), kind)
              if Path(name).name.lower() in expat_info['binaries'] else (name, source, kind)
              for name, source, kind in a.binaries]
a.datas += [('licenses/Python-LICENSE.txt', str(expat_dir / 'Python-LICENSE.txt'), 'DATA'),
            ('licenses/Expat-COPYING.txt', str(expat_dir / 'Expat-COPYING.txt'), 'DATA')]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='DirectorCalendar', console=False,
          icon=str(root / 'director_control/assets/director-calendar.ico'), version=info, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name='DirectorCalendar', upx=False)
