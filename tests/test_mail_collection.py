"""Mail.ru collection metadata must not block disappearance reconciliation."""
from xml.etree.ElementTree import fromstring
from xml.sax.saxutils import escape

import pytest

from director_control.mail_calendar import CALDAV, DAV, CalendarError, fetch_snapshot
from tests.test_mail_calendar import (
    CONFIG, END, START, URL, calendar, dav_response, event, multistatus, sequence_transport,
)


def collection_response(href=URL, *, type_code=200, types=None, data_code=404):
    types = '<d:collection/><c:calendar/>' if types is None else types
    return ('<d:response><d:href>' + escape(href) + '</d:href>'
            '<d:propstat><d:prop><d:resourcetype>' + types + '</d:resourcetype></d:prop>'
            f'<d:status>HTTP/1.0 {type_code}</d:status></d:propstat>'
            '<d:propstat><d:prop><c:calendar-data/></d:prop>'
            f'<d:status>HTTP/1.0 {data_code}</d:status></d:propstat></d:response>')


@pytest.mark.parametrize('position', [0, 1])
def test_selected_collection_metadata_does_not_make_event_query_partial(monkeypatch, position):
    responses = [dav_response(calendar(event('real-event')), href=URL+'real.ics')]
    responses.insert(position, collection_response())
    calls = sequence_transport(monkeypatch, (207, multistatus(*responses)))
    snapshot = fetch_snapshot(CONFIG, 'test-only-secret', START, END)
    assert snapshot.complete and len(snapshot.events) == 1 and not snapshot.unavailable
    assert [call[0] for call in calls] == ['REPORT']
    properties = fromstring(calls[0][2]['data']).find(f'{{{DAV}}}prop')
    assert properties.find(f'{{{DAV}}}resourcetype') is not None
    assert properties.find(f'{{{CALDAV}}}calendar-data') is not None


def test_verified_empty_collection_is_a_complete_empty_query(monkeypatch):
    calls = sequence_transport(monkeypatch, (207, multistatus(collection_response())))
    snapshot = fetch_snapshot(CONFIG, 'test-only-secret', START, END)
    assert snapshot.complete and not snapshot.events
    assert len(calls) == 1


@pytest.mark.parametrize('href', [
    'https://evil.test/calendar/', 'http://calendar.mail.ru/other/',
    'https://calendar.mail.ru/other/', URL+'?private=secret', URL+'#secret',
    URL+'%252e%252e/', 'https://user:secret@calendar.mail.ru/test/',
])
def test_other_or_unsafe_collection_never_confirms_completeness(monkeypatch, href):
    calls = sequence_transport(monkeypatch, (207, multistatus(
        dav_response(calendar(event())), collection_response(href))))
    snapshot = fetch_snapshot(CONFIG, 'test-only-secret', START, END)
    assert not snapshot.complete and len(snapshot.unavailable) == 1
    assert len(calls) == 1 and 'secret' not in snapshot.unavailable[0]


@pytest.mark.parametrize('types,type_code', [
    ('', 200), ('<d:collection/>', 200), ('<c:calendar/>', 200),
    ('<d:collection/><c:calendar/>', 404), ('<d:collection/><c:calendar/>', 403),
])
def test_collection_identity_requires_successful_explicit_calendar_type(monkeypatch, types, type_code):
    calls = sequence_transport(monkeypatch, (207, multistatus(
        dav_response(calendar(event())), collection_response(types=types, type_code=type_code))))
    snapshot = fetch_snapshot(CONFIG, 'test-only-secret', START, END)
    assert not snapshot.complete and len(calls) == 1


def test_collection_type_does_not_hide_access_denial(monkeypatch):
    sequence_transport(monkeypatch, (207, multistatus(collection_response(data_code=403))))
    with pytest.raises(CalendarError, match='calendar-data: 403'):
        fetch_snapshot(CONFIG, 'test-only-secret', START, END)


def test_unreadable_child_still_blocks_disappearance_detection(monkeypatch):
    calls = sequence_transport(monkeypatch, (207, multistatus(
        collection_response(), dav_response(calendar(event())),
        dav_response(code=404, href=URL+'missing.ics'))), (404, b'unavailable'))
    snapshot = fetch_snapshot(CONFIG, 'test-only-secret', START, END)
    assert not snapshot.complete and len(snapshot.events) == 1
    assert len(snapshot.unavailable) == 1 and 'GET 404' in snapshot.unavailable[0]
    assert [call[0] for call in calls] == ['REPORT', 'GET']


def test_child_claiming_collection_type_cannot_be_silently_skipped(monkeypatch):
    calls = sequence_transport(monkeypatch, (207, multistatus(
        collection_response(), dav_response(calendar(event())),
        collection_response(href=URL+'child.ics'))), (404, b'unavailable'))
    snapshot = fetch_snapshot(CONFIG, 'test-only-secret', START, END)
    assert not snapshot.complete and len(calls) == 2
