"""Verified native runtime versions for the published Windows distribution."""
import platform
import pyexpat
import ssl
import struct
import sysconfig

PYTHON_VERSION = '3.14.10'
EXPAT_VERSION = 'expat_2.9.0'
OPENSSL_VERSION = 'OpenSSL 3.5.9 29 Sep 2026'


def runtime_versions():
    return dict(python_version=platform.python_version(),
                python_implementation=platform.python_implementation(),
                python_bits=struct.calcsize('P') * 8,
                python_free_threaded=bool(sysconfig.get_config_var('Py_GIL_DISABLED')),
                expat_version=pyexpat.EXPAT_VERSION,
                # OpenSSL 3.x keeps a legacy zero in VERSION_INFO's third field;
                # its first three integers do not represent the patch version.
                openssl_version=ssl.OPENSSL_VERSION)


def verify_runtime(report):
    """Fail publication if the executable loaded a different native runtime."""
    expected = dict(python_version=PYTHON_VERSION, python_implementation='CPython',
                    python_bits=64, python_free_threaded=False,
                    expat_version=EXPAT_VERSION, openssl_version=OPENSSL_VERSION)
    for key, value in expected.items():
        if type(report.get(key)) is not type(value) or report[key] != value:
            raise ValueError(f'The distribution did not load the pinned runtime: {key}.')
