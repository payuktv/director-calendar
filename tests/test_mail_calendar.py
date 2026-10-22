from datetime import date
from dataclasses import replace
from xml.sax.saxutils import escape

import pytest

from director_control.mail_calendar import (
    CalendarConfig, CalendarError, fetch_snapshot, parse_calendars,
)
from director_control.storage import Store

URL = "https://calendar.mail.ru/principals/example.test/demo/calendars/test/"
CONFIG = CalendarConfig(URL, "demo@example.test")
START, END = date(2026, 10, 20), date(2026, 11, 1)


def calendar(*events):
    return "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Test//EN\r\n" + "".join(
        "BEGIN:VEVENT\r\n" + e.replace("\n", "\r\n") + "\r\nEND:VEVENT\r\n" for e in events
    ) + "END:VCALENDAR\r\n"


def event(uid="test", extra="", start="20261022T090000Z", end="20261022T100000Z"):
    return f"UID:{uid}\nDTSTART:{start}\nDTEND:{end}\nSUMMARY:Test meeting" + ("\n" + extra if extra else "")


def parse(*items):
    return parse_calendars([calendar(*items)], CONFIG, START, END)


def test_single_uid_remains_stable_when_rescheduled_and_utc_is_converted():
    a = parse(event()).events[0]
    b = parse(event(start="20261023T100000Z", end="20261023T110000Z")).events[0]
    assert a.key == b.key
    assert a.start == "2026-10-22T12:00:00"
    assert b.start == "2026-10-23T13:00:00"


def test_recurrence_exdate_and_moved_override_keep_original_identity():
    master = event(extra="RRULE:FREQ=DAILY;COUNT=4\nEXDATE:20261023T090000Z")
    snapshot = parse(master)
    assert len(snapshot.events) == 3
    override = event(extra="RECURRENCE-ID:20261024T090000Z", start="20261025T110000Z", end="20261025T120000Z")
    updated = parse(master, override)
    old = next(e for e in snapshot.events if e.start.startswith("2026-10-24"))
    new = next(e for e in updated.events if e.recurrence_id == old.recurrence_id)
    assert old.key == new.key
    assert new.start == "2026-10-25T14:00:00"
    assert len({e.key for e in updated.events}) == 3


def test_all_day_and_floating_time():
    snapshot = parse("UID:day\nDTSTART;VALUE=DATE:20261022\nSUMMARY:Holiday",
                     "UID:floating\nDTSTART:20261022T090000\nDTEND:20261022T100000\nSUMMARY:Floating")
    a = next(e for e in snapshot.events if e.uid == "day")
    assert a.all_day and a.start == "2026-10-22T00:00:00" and a.end == "2026-10-23T00:00:00"
    assert next(e for e in snapshot.events if e.uid == "floating").start == "2026-10-22T09:00:00"


def test_explicit_cancellation_is_imported():
    snapshot = parse(event(extra="STATUS:CANCELLED"))
    assert len(snapshot.events) == 1 and snapshot.events[0].cancelled


def test_cancelled_recurrence_override():
    master = event(extra="RRULE:FREQ=DAILY;COUNT=3")
    override = event(extra="RECURRENCE-ID:20261023T090000Z\nSTATUS:CANCELLED",
                     start="20261023T090000Z", end="20261023T100000Z")
    snapshot = parse(master, override)
    cancelled = next(e for e in snapshot.events if e.recurrence_id.startswith("2026-10-23"))
    assert cancelled.cancelled


@pytest.mark.parametrize("bad", [
    "UID:invalid\nDTSTART:broken\nDTEND:20261022T100000Z",
    "DTSTART:20261022T090000Z\nDTEND:20261022T100000Z",
    "UID:invalid\nDTSTART:20261022T090000Z",
])
def test_invalid_event_aborts_full_snapshot(bad):
    with pytest.raises(CalendarError):
        parse(event(), bad)


def test_idempotent_import_preserves_baseline_fact_notes_category_and_local_status(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    first = parse(event())
    assert store.apply_calendar_snapshot(first)["added"] == 1
    ev = store.daily_events("2026-10-22")[0]
    store.freeze_day("2026-10-22")
    store.update_event(ev.id, status="done", actual_start="2026-10-22T12:10:00",
                       actual_end="2026-10-22T13:10:00", note="local note", category="Работа")
    moved = parse(event(start="20261023T100000Z", end="20261023T110000Z", extra="STATUS:CANCELLED"))
    assert store.apply_calendar_snapshot(moved)["updated"] == 1
    final = store.get_event(ev.id)
    assert final.baseline_start == "2026-10-22T12:00:00"
    assert final.current_start == "2026-10-23T13:00:00"
    assert final.status == "done" and final.actual_start == "2026-10-22T12:10:00"
    assert final.note == "local note" and final.category == "Работа"
    history = len(store.audit_log())
    assert store.apply_calendar_snapshot(moved) == {"added": 0, "updated": 0, "missing": 0}
    assert len(store.audit_log()) == history
    assert store.calendar_info()[ev.id]["cancelled"]


def test_source_cancellation_and_restoration_without_local_override(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    store.apply_calendar_snapshot(parse(event(extra="STATUS:CANCELLED")))
    ev = store.daily_events("2026-10-22")[0]
    assert ev.status == "cancelled"
    store.apply_calendar_snapshot(parse(event()))
    assert store.get_event(ev.id).status == "pending"


def test_absence_is_not_deletion_manual_data_and_outside_window_survive(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    store.create_event("Manual", "Работа", "2026-10-22T09:00:00", "2026-10-22T10:00:00")
    store.apply_calendar_snapshot(parse(event()))
    remote = next(e for e in store.daily_events("2026-10-22") if e.source == "caldav")
    empty = parse_calendars([], CONFIG, START, END)
    outside = replace(empty, start="2026-12-01T00:00:00", end="2027-01-01T00:00:00")
    assert store.apply_calendar_snapshot(outside)["missing"] == 0
    assert store.apply_calendar_snapshot(empty)["missing"] == 1
    assert store.get_event(remote.id).status == "pending"
    assert len(store.daily_events("2026-10-22")) == 2
    assert store.calendar_info()[remote.id]["missing"]
    store.apply_calendar_snapshot(parse(event()))
    assert not store.calendar_info()[remote.id]["missing"]


def test_transaction_rolls_back_on_conflicting_key(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    snapshot = parse(event("a"), event("b"))
    second = snapshot.events[1]
    store.create_event("Manual", "Работа", second.start, second.end, external_key=second.key)
    with pytest.raises(ValueError):
        store.apply_calendar_snapshot(snapshot)
    assert len(store.daily_events("2026-10-22")) == 1
    assert not store.get_setting("mail_last_sync")


@pytest.mark.parametrize("url", ["http://calendar.mail.ru/a/", "https://evil.test/a/",
                                  "https://calendar.mail.ru@evil.test/a/", "https://calendar.mail.ru/a/?token=x"])
def test_credentials_cannot_be_sent_to_another_destination(url):
    with pytest.raises(CalendarError):
        CalendarConfig(url, "demo@example.test").validate()


class FakeResponse:
    def __init__(self, status, body):
        self.status_code, self.body = status, body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def iter_content(self, size):
        yield self.body


def install_transport(monkeypatch, status=207, body=None):
    calls = []
    class Session:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def request(self, method, url, **kwargs):
            calls.append((method, url, kwargs))
            return FakeResponse(status, body or b'<d:multistatus xmlns:d="DAV:"/>')
    monkeypatch.setattr("director_control.mail_calendar.requests.Session", Session)
    return calls


def test_transport_only_reports_and_imports_complete_xml(monkeypatch):
    body = ('<d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:response>'
            '<d:propstat><d:prop><c:calendar-data>' + escape(calendar(event())) +
            '</c:calendar-data></d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat>'
            '</d:response></d:multistatus>').encode()
    calls = install_transport(monkeypatch, body=body)
    snapshot = fetch_snapshot(CONFIG, "test-only-secret", START, END)
    assert len(snapshot.events) == 1
    method, url, kwargs = calls[0]
    assert method == "REPORT" and url == URL
    assert not kwargs["allow_redirects"] and kwargs["timeout"] == (10, 45)
    assert kwargs["auth"] == (CONFIG.username, "test-only-secret")


@pytest.mark.parametrize("code", [301, 401, 403, 429, 500])
def test_http_failures_do_not_leak_secret_or_response_body(monkeypatch, code):
    install_transport(monkeypatch, status=code, body=b"test-only-secret")
    with pytest.raises(CalendarError) as exc:
        fetch_snapshot(CONFIG, "test-only-secret", START, END)
    assert "test-only-secret" not in str(exc.value)


def test_partial_response_aborts_instead_of_marking_everything_missing(monkeypatch):
    install_transport(monkeypatch, body=b'<d:multistatus xmlns:d="DAV:"><d:response><d:propstat>'
                      b'<d:status>HTTP/1.1 403 Forbidden</d:status></d:propstat></d:response></d:multistatus>')
    with pytest.raises(CalendarError):
        fetch_snapshot(CONFIG, "test-only-secret", START, END)


def test_existing_database_migrates_without_losing_events(tmp_path):
    import sqlite3
    store = Store(tmp_path / "db.sqlite")
    eid = store.create_event("Existing", "Работа", "2026-10-22T09:00:00", "2026-10-22T10:00:00")
    store.freeze_day("2026-10-22")
    with sqlite3.connect(store.path) as con:
        con.execute("DROP TABLE calendar_events")
        con.execute("PRAGMA user_version=0")
    migrated = Store(store.path)
    assert migrated.get_event(eid).baseline_start == "2026-10-22T09:00:00"
    assert migrated.calendar_info() == {}


def test_multiday_all_day_is_visible_without_consuming_working_hours(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    store.apply_calendar_snapshot(parse("UID:holiday\nDTSTART;VALUE=DATE:20261022\nDTEND;VALUE=DATE:20261025\nSUMMARY:Holiday"))
    assert len(store.daily_events("2026-10-23")) == 1
    assert store.coverage_for_day("2026-10-23")["gaps"] == [("07:00", "19:00")]
    store.freeze_day("2026-10-22")
    assert store.day_summary("2026-10-22")["planned"] == 0
    assert all(minutes == 0 for _, minutes, _ in store.category_totals("2026-10-22"))


def test_timezone_and_dst_follow_source_tzid():
    snapshot = parse("UID:dst\nDTSTART;TZID=Europe/Berlin:20261024T100000\n"
                     "DTEND;TZID=Europe/Berlin:20261024T110000\nRRULE:FREQ=DAILY;COUNT=3\nSUMMARY:DST")
    assert [e.start for e in sorted(snapshot.events, key=lambda e: e.start)] == [
        "2026-10-24T11:00:00", "2026-10-25T12:00:00", "2026-10-26T12:00:00"]


def test_recurring_instance_uid_is_scoped_to_calendar_account():
    blob = calendar(event())
    other = CalendarConfig(URL, "other@example.test")
    assert parse_calendars([blob], CONFIG, START, END).events[0].key != parse_calendars([blob], other, START, END).events[0].key


def test_source_plan_fields_cannot_be_overwritten_locally(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    store.apply_calendar_snapshot(parse(event()))
    ev = store.daily_events("2026-10-22")[0]
    with pytest.raises(ValueError):
        store.update_event(ev.id, title="Local change")
    with pytest.raises(ValueError):
        store.delete_event(ev.id)


def test_xml_entities_are_rejected(monkeypatch):
    install_transport(monkeypatch, body=b'<!DOCTYPE test [<!ENTITY x "test-only-secret">]>'
                      b'<d:multistatus xmlns:d="DAV:">&x;</d:multistatus>')
    with pytest.raises(CalendarError):
        fetch_snapshot(CONFIG, "test-only-secret", START, END)


@pytest.mark.parametrize("status", ["HTTP/1.1 200 OK", "HTTP/1.1 200", "HTTP/2 200"])
def test_optional_property_failure_does_not_hide_accessible_calendar_data(monkeypatch, status):
    body = ('<d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:response>'
            '<d:propstat><d:prop><d:getetag/></d:prop><d:status>HTTP/1.1 404 Not Found</d:status></d:propstat>'
            '<d:propstat><d:prop><c:calendar-data>' + escape(calendar(event())) +
            '</c:calendar-data></d:prop><d:status>' + status + '</d:status></d:propstat>'
            '</d:response></d:multistatus>').encode()
    install_transport(monkeypatch, body=body)
    assert len(fetch_snapshot(CONFIG, "test-only-secret", START, END).events) == 1


def test_missing_calendar_data_has_safe_actionable_diagnostics(monkeypatch):
    install_transport(monkeypatch, body=b'<d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
                      b'<d:response><d:href>private-person-and-secret</d:href><d:propstat><d:prop>'
                      b'<c:calendar-data/></d:prop><d:status>HTTP/1.1 403 private-secret</d:status>'
                      b'</d:propstat></d:response></d:multistatus>')
    with pytest.raises(CalendarError) as exc:
        fetch_snapshot(CONFIG, "test-only-secret", START, END)
    assert "calendar-data: 403" in str(exc.value)
    assert "private" not in str(exc.value) and "secret" not in str(exc.value)


def test_one_unreadable_resource_still_aborts_the_whole_import(monkeypatch):
    body = ('<d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:response>'
            '<d:propstat><d:prop><c:calendar-data>' + escape(calendar(event())) +
            '</c:calendar-data></d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>'
            '<d:response><d:propstat><d:prop><c:calendar-data/></d:prop>'
            '<d:status>HTTP/1.1 403 Forbidden</d:status></d:propstat></d:response></d:multistatus>').encode()
    install_transport(monkeypatch, body=body)
    with pytest.raises(CalendarError, match="ресурс 2 из 2"):
        fetch_snapshot(CONFIG, "test-only-secret", START, END)
