from tests.helpers import seed_event, source_update

import pytest

from director_control.storage import Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "db" / "test.db")


def make(store, day="2026-10-22", title="Плановое совещание", start="09:00", end="10:00"):
    return seed_event(store, title, "Совещания", f"{day}T{start}:00", f"{day}T{end}:00")


def test_imported_fixture_persists_and_is_initially_unfixed(store):
    event_id = make(store)
    assert store.get_event(event_id).title == "Плановое совещание"
    assert store.daily_events("2026-10-22")[0].id == event_id
    assert store.day_summary("2026-10-22")["planned"] == 0
    assert store.day_summary("2026-10-22")["unplanned"] == 0
    assert store.day_summary("2026-10-22")["unfixed"] == 1


def test_snapshot_is_immutable_after_reschedule(store):
    eid = make(store)
    assert store.freeze_day("2026-10-22") == 1
    source_update(store, eid, current_start="2026-10-22T11:00:00", current_end="2026-10-22T12:00:00")
    ev = store.get_event(eid)
    assert ev.baseline_start == "2026-10-22T09:00:00"
    assert ev.current_start == "2026-10-22T11:00:00"
    with pytest.raises(ValueError, match="уже зафиксирован"):
        store.freeze_day("2026-10-22")


def test_recurrence_is_handled_as_distinct_occurrences(store):
    a = make(store, "2026-10-22")
    b = make(store, "2026-10-23")
    store.freeze_day("2026-10-22")
    store.freeze_day("2026-10-23")
    store.update_event(a, status="done")
    assert store.day_summary("2026-10-22")["done"] == 1
    assert store.day_summary("2026-10-23")["done"] == 0
    assert store.get_event(b).status == "pending"


def test_planned_executed_and_unplanned_summary(store):
    done = make(store)
    cancelled = make(store, title="Отменённое", start="10:00", end="11:00")
    store.freeze_day("2026-10-22")
    store.update_event(done, status="done", actual_start="2026-10-22T09:00:00", actual_end="2026-10-22T10:20:00")
    store.update_event(cancelled, status="cancelled")
    make(store, title="Срочно вне плана", start="12:00", end="13:00")
    summary = store.day_summary("2026-10-22")
    assert (summary["planned"], summary["done"], summary["cancelled"], summary["unplanned"]) == (2, 1, 1, 1)
    assert summary["percent"] == 50.0
    assert store.category_totals("2026-10-22") == [("Совещания", 120, 80)]


def test_moved_across_days_is_visible_in_both(store):
    eid = make(store)
    store.freeze_day("2026-10-22")
    source_update(store, eid, current_start="2026-10-23T09:00:00", current_end="2026-10-23T10:00:00", status="moved")
    assert len(store.daily_events("2026-10-22")) == 1
    assert len(store.daily_events("2026-10-23")) == 1
    assert store.day_summary("2026-10-22")["planned"] == 1
    assert store.day_summary("2026-10-23")["unplanned"] == 0


def test_local_creation_is_separate_from_import_and_cannot_delete_mail(store):
    mail_id = make(store)
    local_id = store.create_event("Срочно", "Работа", actual_start="2026-10-22T11:00:00",
                                  actual_end="2026-10-22T11:30:00")
    assert store.get_event(local_id).source == "local"
    with pytest.raises(ValueError, match="Mail.ru"):
        store.delete_event(mail_id)
    store.delete_event(local_id)
    assert [event.id for event in store.daily_events("2026-10-22")] == [mail_id]


def test_invalid_time_and_incomplete_fact_are_rejected(store):
    with pytest.raises(ValueError, match="позже начала"):
        make(store, end="08:00")
    eid = make(store)
    with pytest.raises(ValueError, match="оба времени"):
        store.update_event(eid, actual_start="2026-10-22T09:00:00")
    with pytest.raises(ValueError, match="статус"):
        store.update_event(eid, status="anything")


def test_tracking_categories_can_be_configured(store):
    road = seed_event(store, "Дорога", "Дорога", "2026-10-22T08:00:00", "2026-10-22T09:00:00")
    store.freeze_day("2026-10-22")
    assert store.day_summary("2026-10-22")["planned"] == 0
    store.set_category_tracking("Дорога", True)
    assert store.day_summary("2026-10-22")["planned"] == 0
    seed_event(store, "Дорога завтра", "Дорога", "2026-10-23T08:00:00", "2026-10-23T09:00:00")
    store.freeze_day("2026-10-23")
    assert store.day_summary("2026-10-23")["planned"] == 1
    assert store.get_event(road).baseline_start


def test_csv_escapes_excel_formulas_and_uses_bom(store, tmp_path):
    eid = make(store, title="=HYPERLINK('unsafe')")
    store.update_event(eid, note="@SUM(3)")
    file = tmp_path / "out.csv"
    store.export_csv("2026-10-22", file)
    raw = file.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    assert "'=HYPERLINK" in text
    assert "'@SUM(3)" in text


def test_backup_preserves_records(store):
    import sqlite3
    eid = make(store)
    backup = store.backup()
    with sqlite3.connect(backup) as con:
        assert con.execute("SELECT title FROM events WHERE id=?", (eid,)).fetchone()[0] == "Плановое совещание"


def test_history_audit_and_persistence(store):
    eid = make(store)
    store.update_event(eid, status="done")
    assert store.audit_log()[0]["action"] == "Изменение"
    another = Store(store.path)
    assert another.get_event(eid).status == "done"


def test_coverage_detects_gaps_overlaps_and_cancellations(store):
    day = "2026-10-22"
    make(store, start="07:00", end="09:00")
    make(store, title="Overlap", start="08:30", end="10:00")
    c = make(store, title="Cancelled", start="10:00", end="11:00")
    store.update_event(c, status="cancelled")
    coverage = store.coverage_for_day(day)
    assert coverage["gaps"] == [("10:00", "19:00")]
    assert coverage["overlaps"] == 1

