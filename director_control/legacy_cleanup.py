"""Recognize and remove the exact journal trace left by the retired example generator."""
import json
from datetime import date


# Historical fingerprints only. There is no API to create or display sample schedules.
_SAMPLES = (
    ("Утренние мероприятия", "07:00", "08:00"),
    ("Дорога в офис", "08:00", "09:00"),
    ("Совещание с руководителями", "09:00", "10:00"),
    ("Работа с документами", "10:00", "11:30"),
    ("Встреча с партнёрами", "11:30", "12:30"),
    ("Резерв", "12:30", "13:00"),
    ("Обед", "13:00", "14:00"),
    ("Рабочие вопросы", "14:00", "16:00"),
    ("Встреча с подрядчиком", "16:00", "17:00"),
    ("Дорога", "17:00", "18:00"),
    ("Тренировка по боксу", "18:00", "19:00"),
)


def _batch(con, first_id):
    rows = con.execute("SELECT * FROM audit WHERE id>=? ORDER BY id LIMIT 28", (first_id,)).fetchall()
    if len(rows) != 28:
        return None
    try:
        day = json.loads(rows[0]["details"])["start"][:10]
        date.fromisoformat(day)
        ids = []
        for row, (title, start, end) in zip(rows[:11], _SAMPLES):
            expected = {"start": f"{day}T{start}:00", "end": f"{day}T{end}:00"}
            if row["action"] != "Создание" or row["title"] != title or json.loads(row["details"]) != expected:
                return None
            event = con.execute("SELECT * FROM events WHERE id=?", (row["event_id"],)).fetchone()
            if (event is None or event["source"] != "manual" or event["external_key"] is not None
                    or event["baseline_start"] != expected["start"] or event["baseline_end"] != expected["end"]):
                return None
            ids.append(event["id"])
        if len(set(ids)) != 11:
            return None
        for row, event_id in zip(rows[11:22], ids):
            if (row["action"] != "Фиксация плана" or row["event_id"] != event_id
                    or json.loads(row["details"]) != {"day": day}):
                return None
        for row, (index, status, start, end, note) in zip(rows[22:], (
            (0, "done", "07:00", "08:00", None),
            (2, "done", "09:00", "10:20", "Совещание завершилось позднее"),
            (3, "partial", "10:20", "11:30", None),
            (4, "done", "11:30", "12:30", None),
            (8, "moved", None, None, "Перенос на следующий день (демо)"),
            (10, "cancelled", None, None, "Решение руководителя (демо)"),
        )):
            expected = {"status": {"было": "pending", "стало": status}}
            if start:
                expected["actual_start"] = {"было": None, "стало": f"{day}T{start}:00"}
                expected["actual_end"] = {"было": None, "стало": f"{day}T{end}:00"}
            if note:
                expected["note"] = {"было": "", "стало": note}
            if (row["action"] != "Изменение" or row["event_id"] != ids[index]
                    or json.loads(row["details"]) != expected):
                return None
        return day, ids
    except (KeyError, ValueError, TypeError):
        return None


def remove_legacy_examples(store):
    with store._connect() as con:
        candidates = con.execute("SELECT id FROM audit WHERE action='Создание' AND title=?",
                                 (_SAMPLES[0][0],)).fetchall()
        if not candidates:
            return
        con.execute("BEGIN IMMEDIATE")
        batches = [batch for row in candidates if (batch := _batch(con, row["id"]))]
        if not batches:
            return
        # Failure to make the reversible safety copy prevents deletion.
        store.backup()
        removed = 0
        for day, ids in batches:
            placeholders = ",".join("?" for _ in ids)
            con.execute(f"DELETE FROM audit WHERE event_id IN ({placeholders})", ids)
            con.execute(f"DELETE FROM events WHERE id IN ({placeholders})", ids)
            # Allow a real Mail.ru plan to be frozen after the example is gone.
            if not con.execute("SELECT 1 FROM events WHERE substr(baseline_start,1,10)=? LIMIT 1", (day,)).fetchone():
                con.execute("DELETE FROM day_freezes WHERE day=?", (day,))
            removed += len(ids)
        store._audit(con, None, "Обслуживание базы", "Очистка старых примеров", {"удалено": removed})
