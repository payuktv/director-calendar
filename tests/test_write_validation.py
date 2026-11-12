"""Accepted writes must stay valid at startup; rejected input must not change data."""
from dataclasses import replace

import pytest

from director_control import __version__
from director_control.backups import validate_database
from director_control.mail_calendar import CalendarError, fetch_snapshot
from director_control.storage import Store
from director_control.sync_process import parse_isolated
from director_control.updates import prepare_version_update
from tests.test_mail_calendar import (
    CONFIG, START, END, calendar, event, parse, install_transport, multistatus, dav_response,
)


def existing_store(tmp_path):
    store = Store(tmp_path / 'records.db')
    store.set_setting('app_last_version', __version__)
    store.apply_calendar_snapshot(parse(event('existing')))
    return store


def assert_reopens(store):
    validate_database(store.path)
    assert prepare_version_update(store.path) is None
    reopened = Store(store.path)
    assert reopened.daily_events('2026-10-22') == store.daily_events('2026-10-22')


@pytest.mark.parametrize('uid', ['   ', r'\n', 'private\0uid'])
def test_invalid_uid_aborts_transport_without_modifying_existing_data(tmp_path, monkeypatch, uid):
    store = existing_store(tmp_path)
    before = store.path.read_bytes()
    body = multistatus(dav_response(calendar(event('valid-new'), event(uid))))
    install_transport(monkeypatch, body=body)
    with pytest.raises(CalendarError) as error:
        store.apply_calendar_snapshot(fetch_snapshot(CONFIG, 'synthetic', START, END))
    assert 'private' not in str(error.value)
    assert store.path.read_bytes() == before
    assert_reopens(store)


@pytest.mark.parametrize('uid', ['   ', r'\n'])
def test_real_worker_rejects_invalid_uid(tmp_path, uid):
    store = existing_store(tmp_path)
    before = store.path.read_bytes()
    with pytest.raises(CalendarError):
        store.apply_calendar_snapshot(parse_isolated([calendar(event(uid))], CONFIG, START, END))
    assert store.path.read_bytes() == before
    assert_reopens(store)


@pytest.mark.parametrize('fields', [
    {'uid': '   '}, {'uid': '\n'}, {'uid': 'private\0uid'},
    {'key': ''}, {'key': b'private'}, {'recurrence_id': 'private\0rid'},
    {'title': 'private\0title'}, {'title': b'private'}, {'title': ' '}, {'title': 'a' * 201},
    {'start': '2026-10-22 12:00:00'}, {'start': '20261022T120000'},
    {'start': '2026-10-22T12:00:00+03:00'}, {'start': None, 'end': None},
    {'cancelled': 2}, {'all_day': '0'},
])
def test_storage_rejects_entire_snapshot_before_any_write(tmp_path, fields):
    store = existing_store(tmp_path)
    before = store.path.read_bytes()
    snapshot = parse(event('valid-new'), event('invalid-new'))
    snapshot = replace(snapshot, events=(snapshot.events[0], replace(snapshot.events[1], **fields)))
    with pytest.raises(ValueError) as error:
        store.apply_calendar_snapshot(snapshot)
    assert 'private' not in str(error.value)
    assert store.path.read_bytes() == before
    assert_reopens(store)


@pytest.mark.parametrize('fields', [
    {'calendar_key': ' '}, {'calendar_key': 'private\0key'},
    {'start': None, 'end': None}, {'start': '2026-10-20 00:00:00'},
])
def test_invalid_empty_snapshot_cannot_withdraw_events_or_write_sync_metadata(tmp_path, fields):
    store = existing_store(tmp_path)
    before = store.path.read_bytes()
    with pytest.raises(ValueError):
        store.apply_calendar_snapshot(replace(parse(), **fields))
    assert store.path.read_bytes() == before
    assert_reopens(store)


def test_valid_identity_is_not_trimmed_and_survives_restart_and_source_removal(tmp_path):
    store = Store(tmp_path / 'valid.db')
    store.set_setting('app_last_version', __version__)
    snapshot = parse_isolated([calendar(event(' uid with spaces '))], CONFIG, START, END)
    original = snapshot.events[0]
    assert original.uid == ' uid with spaces '
    assert store.apply_calendar_snapshot(snapshot)['added'] == 1
    assert store.apply_calendar_snapshot(snapshot)['added'] == 0
    eid = store.daily_events('2026-10-22')[0].id
    store.update_event(eid, note='Заметка\nВторая строка', status='cancelled')
    assert_reopens(store)
    store.apply_calendar_snapshot(replace(snapshot, events=()))
    assert_reopens(store)
    store.apply_calendar_snapshot(snapshot)
    assert store.get_event(eid).status == 'cancelled'
    assert store.get_event(eid).note == 'Заметка\nВторая строка'
    assert store.calendar_info()[eid]['uid'] == original.uid
    assert_reopens(store)


@pytest.mark.parametrize('field,value', [('note', 'private\0note'), ('note', b'private'),
                                         ('title', 'private\0title')])
@pytest.mark.parametrize('update', [False, True])
def test_local_writes_reject_invalid_text_and_preserve_original(tmp_path, field, value, update):
    store = existing_store(tmp_path)
    data = dict(title='Local', category='Работа', current_start='2026-10-22T09:00:00',
                current_end='2026-10-22T10:00:00', note='keep')
    eid = store.create_event(**data)
    before = store.path.read_bytes()
    with pytest.raises(ValueError):
        if update:
            store.update_event(eid, **{field: value})
        else:
            store.create_event(**(data | {field: value}))
    assert store.path.read_bytes() == before
    assert_reopens(store)


@pytest.mark.parametrize('name,track', [('private\0category', True), ('Category', 2)])
def test_category_write_cannot_invalidate_saved_records(tmp_path, name, track):
    store = existing_store(tmp_path)
    before = store.path.read_bytes()
    with pytest.raises(ValueError):
        store.add_category(name, track)
    assert store.path.read_bytes() == before
    assert_reopens(store)


def test_tracking_and_failure_metadata_are_checked_before_writes(tmp_path):
    store = existing_store(tmp_path)
    before = store.path.read_bytes()
    for operation in (lambda: store.set_category_tracking('Работа', 2),
                      lambda: store.record_sync_failure(' ', START, END)):
        with pytest.raises(ValueError):
            operation()
        assert store.path.read_bytes() == before
    store.record_sync_failure(CONFIG.calendar_key, START, END)
    store.freeze_day('20261022')
    assert store.is_frozen('2026-10-22')
    assert_reopens(store)


@pytest.mark.parametrize('declaration', [
    b'<!DOCTYPE d:multistatus [<!ELEMENT d:multistatus ANY>]>',
    b'<!DOCTYPE d:multistatus SYSTEM "file:///must-not-be-opened">',
    b'<!DOCTYPE d:multistatus [<!ENTITY unused "synthetic">]>',
])
def test_production_transport_rejects_dtd_without_changing_database(tmp_path, monkeypatch, declaration):
    store = existing_store(tmp_path)
    before = store.path.read_bytes()
    install_transport(monkeypatch, body=declaration + multistatus())
    with pytest.raises(CalendarError):
        store.apply_calendar_snapshot(fetch_snapshot(CONFIG, 'synthetic', START, END))
    assert store.path.read_bytes() == before
    assert_reopens(store)


def test_plain_xml_still_imports_and_reopens(tmp_path, monkeypatch):
    store = existing_store(tmp_path)
    install_transport(monkeypatch, body=multistatus(dav_response(calendar(event('ordinary')))))
    assert store.apply_calendar_snapshot(fetch_snapshot(CONFIG, 'synthetic', START, END))['added'] == 1
    assert_reopens(store)


def test_shipped_write_acceptance_uses_temporary_records(tmp_path):
    from director_control.distribution_check import _verify_calendar_writes
    _verify_calendar_writes(tmp_path)
