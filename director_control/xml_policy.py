"""The same untrusted XML policy for CalDAV and distribution acceptance."""
from defusedxml.ElementTree import fromstring


def parse_untrusted_xml(body):
    return fromstring(body, forbid_dtd=True, forbid_entities=True, forbid_external=True)
