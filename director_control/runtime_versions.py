"""Verified native runtime versions for the published Windows distribution."""
import platform
import pyexpat
import ssl
import struct
import sysconfig

PYTHON_VERSION = '3.14.10'
EXPAT_VERSION = 'expat_2.10.0'
OPENSSL_VERSION = 'OpenSSL 3.5.9 29 Sep 2026'


def runtime_versions():
    import _elementtree
    from xml.etree import ElementTree
    return dict(python_version=platform.python_version(),
                python_implementation=platform.python_implementation(),
                python_bits=struct.calcsize('P') * 8,
                python_free_threaded=bool(sysconfig.get_config_var('Py_GIL_DISABLED')),
                expat_version=pyexpat.EXPAT_VERSION,
                elementtree_version=ElementTree.XMLParser().version,
                elementtree_accelerated=ElementTree.XMLParser is _elementtree.XMLParser,
                # OpenSSL 3.x keeps a legacy zero in VERSION_INFO's third field;
                # its first three integers do not represent the patch version.
                openssl_version=ssl.OPENSSL_VERSION)


def verify_runtime(report):
    """Fail publication if the executable loaded a different native runtime."""
    expected = dict(python_version=PYTHON_VERSION, python_implementation='CPython',
                    python_bits=64, python_free_threaded=False,
                    expat_version=EXPAT_VERSION, elementtree_version='Expat 2.10.0',
                    elementtree_accelerated=True, openssl_version=OPENSSL_VERSION)
    for key, value in expected.items():
        if type(report.get(key)) is not type(value) or report[key] != value:
            raise ValueError(f'The distribution did not load the pinned runtime: {key}.')


def verify_xml_runtime():
    """Exercise both rebuilt modules, including the fixed empty subparser path."""
    import _elementtree
    from xml.etree import ElementTree
    from defusedxml.common import DefusedXmlException
    from .xml_policy import parse_untrusted_xml

    if (pyexpat.EXPAT_VERSION != EXPAT_VERSION or ElementTree.XMLParser is not _elementtree.XMLParser
            or ElementTree.XMLParser().version != 'Expat 2.10.0'):
        raise ValueError('The paired XML runtime was not updated')
    body = '<r xmlns="urn:test"><title>Календарь &amp; план</title></r>'.encode('utf-8')
    for parse in (ElementTree.fromstring, parse_untrusted_xml):
        if parse(body).findtext('{urn:test}title') != 'Календарь & план':
            raise ValueError('XML runtime failed Unicode/namespace parsing')
    for body in (b'<!DOCTYPE r [<!ELEMENT r ANY>]><r/>',
                 b'<!DOCTYPE r [<!ENTITY a "blocked">]><r>&a;</r>',
                 b'<!DOCTYPE r SYSTEM "file:///must-not-be-opened"><r/>'):
        try:
            parse_untrusted_xml(body)
        except DefusedXmlException:
            pass
        else:
            raise ValueError('Untrusted XML entities/DTD were accepted')
    parent = pyexpat.ParserCreate()
    child = parent.ExternalEntityParserCreate('synthetic')
    seen = []
    child.ProcessingInstructionHandler = lambda target, data: seen.append((target, data))
    child.Parse(b'', False)
    child.Parse(b'<?target data?>', True)
    if seen != [('target', 'data')]:
        raise ValueError('XML empty-subparser regression')
