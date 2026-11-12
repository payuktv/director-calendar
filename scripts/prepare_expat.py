"""Build the paired CPython XML extensions with pinned upstream Expat sources.

CPython statically links Expat into pyexpat; _elementtree checks the exact Expat
version in its capsule. Rebuild BOTH against the same headers, without replacing
the system interpreter. Windows needs the MSVC C++ build tools (present in CI).
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import struct
import subprocess
import sys
import sysconfig
import tarfile
import tempfile
from urllib.request import urlopen

PYTHON_VERSION = '3.14.10'
EXPAT_VERSION = '2.10.0'
SOURCES = {
    'python': ('https://www.python.org/ftp/python/3.14.10/Python-3.14.10.tar.xz',
               'de414a57119abef52784d8993e341d53aed635fc2b05c2607d9f98a2c5b72032'),
    'expat': ('https://github.com/libexpat/libexpat/releases/download/R_2_10_0/expat-2.10.0.tar.xz',
              'c624ba2998fc65df1163a49641ff3f9ab73138b11641d92c86bee0fb01b1bc7f'),
}
MAX_DOWNLOAD = 40 * 1024 * 1024
MAX_EXPANDED = 160 * 1024 * 1024


def verified_bytes(data, expected):
    if len(data) > MAX_DOWNLOAD or hashlib.sha256(data).hexdigest() != expected:
        raise ValueError('XML runtime source archive checksum mismatch')
    return data


def download_sources(folder):
    folder.mkdir(parents=True, exist_ok=True)
    archives = {}
    for name, (url, digest) in SOURCES.items():
        archive = folder / (name + '.tar.xz')
        if archive.is_file():
            with archive.open('rb') as cached:
                data = cached.read(MAX_DOWNLOAD + 1)
        else:
            with urlopen(url, timeout=45) as response:
                data = response.read(MAX_DOWNLOAD + 1)
        verified_bytes(data, digest)  # Revalidate cached downloads every time.
        archive.write_bytes(data)
        archives[name] = data
    return archives


def extract_sources(data, destination, prefix):
    """Extract only regular files under a fixed prefix; never follow tar links."""
    total = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:xz') as archive:
        for item in archive:
            path = PurePosixPath(item.name)
            if path.is_absolute() or '..' in path.parts or '\\' in item.name or ':' in item.name:
                raise ValueError('Unsafe XML runtime source archive path')
            if not path.parts or path.parts[0] != prefix:
                raise ValueError('Unexpected XML runtime source archive root')
            relative = path.parts[1:]
            if not relative or item.isdir():
                continue
            name = '/'.join(relative)
            wanted = (name.startswith(('Include/', 'Lib/', 'lib/'))
                      or name in {'PC/pyconfig.h', 'Modules/pyexpat.c', 'Modules/_elementtree.c',
                                  'Modules/clinic/_elementtree.c.h', 'Modules/expat/expat_config.h',
                                  'Modules/expat/pyexpatns.h', 'LICENSE', 'COPYING'})
            if not wanted:
                continue
            total += item.size
            if not item.isfile() or item.size > 8 * 1024 * 1024 or total > MAX_EXPANDED:
                raise ValueError('Unexpected XML runtime source archive member')
            target = destination.joinpath(*relative)
            if not target.resolve().is_relative_to(destination.resolve()):
                raise ValueError('Unsafe XML runtime source archive destination')
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(item) as source, target.open('wb') as output:
                shutil.copyfileobj(source, output)


def build_extensions(python_source, expat_source, build):
    from setuptools import Distribution, Extension
    from setuptools.command.build_ext import build_ext

    includes = [expat_source / 'lib', python_source / 'Modules/expat',
                python_source / 'Include', python_source / 'Include/internal']
    if sys.platform == 'win32':
        includes.append(python_source / 'PC')
    namespace = python_source / 'Modules/expat/pyexpatns.h'
    compile_args = (['/FI' + str(namespace), '/utf-8', '/guard:cf'] if sys.platform == 'win32'
                    else ['-include', str(namespace), '-fvisibility=hidden'])
    link_args = ['/guard:cf', '/DYNAMICBASE', '/NXCOMPAT'] if sys.platform == 'win32' else []
    common = dict(include_dirs=[str(path) for path in includes],
                  define_macros=[('XML_STATIC', '1'), ('PYEXPAT_EXPORTS', '1')],
                  extra_compile_args=compile_args, extra_link_args=link_args)
    extensions = [
        Extension('pyexpat', [str(python_source / 'Modules/pyexpat.c')]
                  + [str(expat_source / 'lib' / name) for name in ('xmlparse.c', 'xmlrole.c', 'xmltok.c', 'xcs.c')],
                  **common),
        Extension('_elementtree', [str(python_source / 'Modules/_elementtree.c')], **common),
    ]
    command = build_ext(Distribution({'name': 'director-xml-runtime', 'ext_modules': extensions}))
    command.ensure_finalized()
    command.build_lib, command.build_temp = str(build / 'lib'), str(build / 'obj')
    command.force = True
    command.run()
    return {extension.name: Path(command.get_ext_fullpath(extension.name)) for extension in extensions}


def verify_extensions(folder, python_source):
    env = dict(os.environ)
    # Upstream regression tests also run with the rebuilt modules, not the ones
    # installed with the interpreter. Source Lib matches that interpreter exactly.
    env['PYTHONPATH'] = os.pathsep.join((str(folder), str(python_source / 'Lib')))
    probe = ("import pyexpat,_elementtree,xml.etree.ElementTree as E; "
             "assert pyexpat.EXPAT_VERSION=='expat_2.10.0'; "
             "assert E.XMLParser is _elementtree.XMLParser; "
             "assert E.XMLParser().version=='Expat 2.10.0'; "
             "assert E.fromstring('<r><a>test</a></r>').findtext('a')=='test'")
    subprocess.run([sys.executable, '-c', probe], env=env, cwd=folder, check=True, timeout=20)
    subprocess.run([sys.executable, '-m', 'test', 'test_pyexpat', 'test_xml_etree', 'test_xml_etree_c'],
                   env=env, cwd=folder, check=True, timeout=180)


def prepare(folder):
    if (platform.python_implementation() != 'CPython' or platform.python_version() != PYTHON_VERSION
            or struct.calcsize('P') != 8 or sysconfig.get_config_var('Py_GIL_DISABLED')
            or sys.platform not in ('win32', 'linux')):
        raise ValueError('XML overlay requires standard CPython 3.14.10 x64 on Windows or Linux')
    folder = folder.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    archives = download_sources(folder)
    with tempfile.TemporaryDirectory(prefix='xml-build-', dir=folder) as temporary:
        work = Path(temporary)
        python_source, expat_source = work / 'python', work / 'expat'
        extract_sources(archives['python'], python_source, 'Python-' + PYTHON_VERSION)
        extract_sources(archives['expat'], expat_source, 'expat-' + EXPAT_VERSION)
        extensions = build_extensions(python_source, expat_source, work / 'build')
        verify_extensions(work / 'build/lib', python_source)
        binaries = {}
        for name, built in extensions.items():
            target = folder / (name + ('.pyd' if sys.platform == 'win32' else '.so'))
            shutil.copyfile(built, target)
            binaries[target.name] = hashlib.sha256(target.read_bytes()).hexdigest()
        shutil.copyfile(python_source / 'LICENSE', folder / 'Python-LICENSE.txt')
        shutil.copyfile(expat_source / 'COPYING', folder / 'Expat-COPYING.txt')
    info = {'python': PYTHON_VERSION, 'expat': EXPAT_VERSION, 'platform': sys.platform,
            'sources': {name: {'url': url, 'sha256': digest} for name, (url, digest) in SOURCES.items()},
            'upstream_tests': ['test_pyexpat', 'test_xml_etree', 'test_xml_etree_c'],
            'binaries': binaries}
    (folder / 'expat-build.json').write_text(json.dumps(info, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(info))
    return folder


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    parser.add_argument('--download-only', action='store_true')
    args = parser.parse_args()
    if args.download_only:
        download_sources(args.folder)
        print('Verified source archives downloaded')
    else:
        prepare(args.folder)
