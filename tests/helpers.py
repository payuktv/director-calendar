"""Test-only fixtures for imported events and pre-Mail.ru legacy databases."""
from dataclasses import asdict
from datetime import date, timedelta

from director_control.storage import Event, Store, STATUSES, now_iso, validate_interval


class LegacyStoreFixture(Store):
    # Historical methods are intentionally isolated from the application.
    def create_event(
        self, title: str, category: str, current_start: str, current_end: str,
        *, source: str = "manual", external_key: str | None = None,
    ) -> int:
        title = title.strip()
        if not title or len(title) > 200:
            raise ValueError("Название мероприятия должно содержать 1–200 символов")
        validate_interval(current_start, current_end)
        with self._connect() as con:
            cur = con.execute("""
                INSERT INTO events (title,category,current_start,current_end,source,external_key,created_at,updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (title, category, current_start, current_end, source, external_key, now_iso(), now_iso()))
            event_id = int(cur.lastrowid)
            self._audit(con, event_id, title, "Создание", {"start": current_start, "end": current_end})
            return event_id

    def update_event(self, event_id: int, **updates: str | None) -> None:
        allowed = {"title", "category", "current_start", "current_end", "actual_start", "actual_end", "status", "note"}
        if not updates or not set(updates).issubset(allowed):
            raise ValueError("Недопустимые поля изменения")
        old = self.get_event(event_id)
        if old.source == "caldav" and any(k in updates and updates[k] != getattr(old, k)
                                          for k in ("title", "current_start", "current_end")):
            raise ValueError("Название и плановое время импортированного события меняются в Mail.ru.")
        data = asdict(old)
        data.update(updates)
        if not str(data["title"]).strip():
            raise ValueError("Название не может быть пустым")
        validate_interval(data["current_start"], data["current_end"], "Актуальный план")
        if bool(data["actual_start"]) != bool(data["actual_end"]):
            raise ValueError("Укажи оба времени факта либо оставь оба пустыми")
        if data["actual_start"]:
            validate_interval(data["actual_start"], data["actual_end"], "Фактическое время")
        if data["status"] not in STATUSES:
            raise ValueError("Неизвестный статус")
        changes = {k: {"было": getattr(old, k), "стало": data[k]} for k in updates if getattr(old, k) != data[k]}
        if not changes:
            return
        with self._connect() as con:
            columns = [f"{k}=?" for k in changes]
            con.execute(f"UPDATE events SET {', '.join(columns)}, updated_at=? WHERE id=?",
                        [data[k] for k in changes] + [now_iso(), event_id])
            if "status" in changes or "actual_start" in changes or "actual_end" in changes:
                con.execute("UPDATE calendar_events SET local_status=1 WHERE event_id=?", (event_id,))
            self._audit(con, event_id, str(data["title"]), "Изменение", changes)

    def freeze_day(self, day: str) -> int:
        date.fromisoformat(day)
        with self._connect() as con:
            if con.execute("SELECT 1 FROM day_freezes WHERE day=?", (day,)).fetchone():
                raise ValueError("Первоначальный план на эту дату уже зафиксирован")
            con.execute("INSERT INTO day_freezes VALUES (?, ?)", (day, now_iso()))
            ids = con.execute("SELECT id, title FROM events WHERE substr(current_start,1,10)=? AND baseline_start IS NULL", (day,)).fetchall()
            con.execute("""UPDATE events SET baseline_start=current_start, baseline_end=current_end
                        WHERE substr(current_start,1,10)=? AND baseline_start IS NULL""", (day,))
            for row in ids:
                con.execute("UPDATE calendar_events SET baseline_all_day=all_day WHERE event_id=?", (row["id"],))
            for row in ids:
                self._audit(con, row["id"], row["title"], "Фиксация плана", {"day": day})
            return len(ids)

    def is_frozen(self, day: str) -> bool:
        with self._connect() as con:
            return con.execute("SELECT 1 FROM day_freezes WHERE day=?", (day,)).fetchone() is not None

    def daily_events(self, day: str) -> list[Event]:
        date.fromisoformat(day)
        start = f"{day}T00:00:00"
        end = (date.fromisoformat(day) + timedelta(days=1)).isoformat() + "T00:00:00"
        with self._connect() as con:
            rows = con.execute("""
                SELECT * FROM events WHERE (current_start<? AND current_end>?)
                OR (baseline_start<? AND baseline_end>?)
                ORDER BY CASE WHEN substr(current_start,1,10)=? THEN current_start ELSE baseline_start END, id
            """, (end, start, end, start, day)).fetchall()
            return [self._as_event(r) for r in rows]



def seed_event(store, title, category, current_start, current_end, *, source="caldav", external_key=None):
    """Populate a test database without restoring a production creation API."""
    event_id = LegacyStoreFixture.create_event(store, title, category, current_start, current_end,
                                              source=source, external_key=external_key)
    if source == "caldav":
        key = external_key or f"fixture:{event_id}"
        with store._connect() as con:
            con.execute("UPDATE events SET external_key=? WHERE id=?", (key, event_id))
            con.execute("INSERT INTO calendar_events(event_id,calendar_key,uid,recurrence_id) VALUES (?,?,?,?)",
                        (event_id, "fixture", key, ""))
    return event_id


def source_update(store, event_id, **updates):
    """Fixture-only source changes; real imports are exercised by CalDAV tests."""
    source_fields = {key: value for key, value in updates.items() if key in {"title", "current_start", "current_end"}}
    if source_fields:
        with store._connect() as con:
            con.execute("UPDATE events SET " + ",".join(key + "=?" for key in source_fields) + " WHERE id=?",
                        [*source_fields.values(), event_id])
    local = {key: value for key, value in updates.items() if key not in source_fields}
    if local:
        store.update_event(event_id, **local)
