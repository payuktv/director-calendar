# Run only on Windows. The source root can point at the previous revision in CI.
import os
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
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='DirectorCalendar', console=False,
          icon=str(root / 'director_control/assets/director-calendar.ico'), version=info, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name='DirectorCalendar', upx=False)
