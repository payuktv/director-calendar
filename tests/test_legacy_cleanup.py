"""Regression fixtures reproduce the retired 0.1 generator, never imported by the app."""
import sqlite3

import pytest

from tests.helpers import LegacyStoreFixture as Store


def old_example(store, day="2026-10-22"):
    # Historical behaviour from release 0.1; the production generator has been removed.
    samples = [
        ("Утренние мероприятия", "Личное", "07:00", "08:00"),
        ("Дорога в офис", "Дорога", "08:00", "09:00"),
        ("Совещание с руководителями", "Совещания", "09:00", "10:00"),
        ("Работа с документами", "Работа", "10:00", "11:30"),
        ("Встреча с партнёрами", "Встречи", "11:30", "12:30"),
        ("Резерв", "Резерв", "12:30", "13:00"),
        ("Обед", "Отдых", "13:00", "14:00"),
        ("Рабочие вопросы", "Работа", "14:00", "16:00"),
        ("Встреча с подрядчиком", "Встречи", "16:00", "17:00"),
        ("Дорога", "Дорога", "17:00", "18:00"),
        ("Тренировка по боксу", "Спорт", "18:00", "19:00"),
    ]
    ids = [store.create_event(t, c, f"{day}T{s}:00", f"{day}T{e}:00") for t, c, s, e in samples]
    store.freeze_day(day)
    store.update_event(ids[0], status="done", actual_start=f"{day}T07:00:00", actual_end=f"{day}T08:00:00")
    store.update_event(ids[2], status="done", actual_start=f"{day}T09:00:00", actual_end=f"{day}T10:20:00", note="Совещание завершилось позднее")
    store.update_event(ids[3], status="partial", actual_start=f"{day}T10:20:00", actual_end=f"{day}T11:30:00")
    store.update_event(ids[4], status="done", actual_start=f"{day}T11:30:00", actual_end=f"{day}T12:30:00")
    store.update_event(ids[8], status="moved", note="Перенос на следующий день (демо)")
    store.update_event(ids[10], status="cancelled", note="Решение руководителя (демо)")
    return ids


def test_known_examples_removed_but_mail_and_real_manual_events_survive(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    old_example(store)
    mail = store.create_event("Утренние мероприятия", "Работа", "2026-10-22T07:00:00", "2026-10-22T08:00:00",
                              source="caldav", external_key="real-mail-event")
    manual = store.create_event("Реальная встреча", "Встречи", "2026-10-22T15:00:00", "2026-10-22T16:00:00")
    store.set_setting("mail_url", "keep-connection")
    reopened = Store(store.path)
    assert {e.id for e in reopened.daily_events("2026-10-22")} == {mail, manual}
    assert reopened.get_setting("mail_url") == "keep-connection"
    assert not reopened.is_frozen("2026-10-22")
    assert all("демо" not in row["details"] for row in reopened.audit_log())
    backups = list((tmp_path / "backups").glob("*.db"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as con:
        assert con.execute("SELECT count(*) FROM events").fetchone()[0] == 13
    Store(store.path)
    assert len(list((tmp_path / "backups").glob("*.db"))) == 1


def test_similar_manual_title_is_not_enough_for_deletion(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    eid = store.create_event("Утренние мероприятия", "Личное", "2026-10-22T07:00:00", "2026-10-22T08:00:00")
    store.freeze_day("2026-10-22")
    assert Store(store.path).get_event(eid).title == "Утренние мероприятия"
    assert not (tmp_path / "backups").exists()


def test_incomplete_or_changed_generation_trace_is_not_removed(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    old_example(store)
    with sqlite3.connect(store.path) as con:
        con.execute("DELETE FROM audit WHERE id=(SELECT max(id) FROM audit)")
    assert len(Store(store.path).daily_events("2026-10-22")) == 11


def test_edited_example_still_recognized_by_original_trace(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    ids = old_example(store)
    store.update_event(ids[0], title="Changed sample", note="Edited sample")
    assert Store(store.path).daily_events("2026-10-22") == []


def test_backup_failure_prevents_cleanup(tmp_path, monkeypatch):
    store = Store(tmp_path / "db.sqlite")
    old_example(store)
    def fail(self):
        raise OSError("test backup failure")
    monkeypatch.setattr(Store, "backup", fail)
    with pytest.raises(OSError):
        Store(store.path)
    with sqlite3.connect(store.path) as con:
        assert con.execute("SELECT count(*) FROM events").fetchone()[0] == 11
        assert con.execute("SELECT count(*) FROM audit").fetchone()[0] == 28


def test_real_frozen_plan_is_preserved(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    old_example(store)
    eid = store.create_event("Real baseline", "Работа", "2026-10-22T14:00:00", "2026-10-22T15:00:00")
    with sqlite3.connect(store.path) as con:
        con.execute("UPDATE events SET baseline_start=current_start, baseline_end=current_end WHERE id=?", (eid,))
    reopened = Store(store.path)
    assert reopened.is_frozen("2026-10-22")
    assert reopened.get_event(eid).baseline_start == "2026-10-22T14:00:00"
