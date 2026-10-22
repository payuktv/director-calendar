"""SQLite data access and plan/fact rules (no GUI dependencies)."""
from __future__ import annotations

import csv
import json
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterator

STATUSES = {
    "pending": "Не подтверждено",
    "done": "Выполнено",
    "partial": "Частично",
    "cancelled": "Отменено",
    "moved": "Перенесено",
}
DEFAULT_CATEGORIES = [
    ("Совещания", "#6678E8", 1),
    ("Встречи", "#27A88A", 1),
    ("Работа", "#55A7D9", 1),
    ("Спорт", "#E7A14E", 1),
    ("Личное", "#AF7CE1", 1),
    ("Дорога", "#7C8A9B", 0),
    ("Отдых", "#8B9EA4", 0),
    ("Резерв", "#BBC5D0", 0),
]


def default_data_dir() -> Path:
    if override := os.environ.get("DIRECTOR_CONTROL_DATA_DIR"):
        return Path(override).expanduser()
    if os.name == "nt":
        root = os.getenv("LOCALAPPDATA")
        return (Path(root) if root else Path.home() / "AppData" / "Local") / "DirectorControl"
    return Path.home() / ".local" / "share" / "director-control"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def validate_interval(start: str, end: str, label: str = "Интервал") -> None:
    try:
        s, e = datetime.fromisoformat(start), datetime.fromisoformat(end)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}: неверный формат даты/времени") from exc
    if s >= e:
        raise ValueError(f"{label}: время окончания должно быть позже начала")


def minutes_between(start: str, end: str) -> int:
    return round((datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds() / 60)


@dataclass(frozen=True)
class Event:
    id: int
    title: str
    category: str
    current_start: str
    current_end: str
    baseline_start: str | None
    baseline_end: str | None
    actual_start: str | None
    actual_end: str | None
    status: str
    note: str
    source: str


class Store:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path is not None else default_data_dir() / "director_control.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self.path, timeout=10)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def _initialize(self) -> None:
        with self._connect() as con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS categories (
                    name TEXT PRIMARY KEY,
                    color TEXT NOT NULL,
                    track INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    category TEXT NOT NULL REFERENCES categories(name),
                    current_start TEXT NOT NULL,
                    current_end TEXT NOT NULL,
                    baseline_start TEXT,
                    baseline_end TEXT,
                    actual_start TEXT,
                    actual_end TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    note TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT 'manual',
                    external_key TEXT UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_events_current ON events(current_start);
                CREATE INDEX IF NOT EXISTS idx_events_baseline ON events(baseline_start);
                CREATE TABLE IF NOT EXISTS day_freezes (
                    day TEXT PRIMARY KEY,
                    frozen_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id INTEGER,
                    title TEXT NOT NULL,
                    action TEXT NOT NULL,
                    details TEXT NOT NULL,
                    changed_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
            """)
            for name, color, track in DEFAULT_CATEGORIES:
                con.execute("INSERT OR IGNORE INTO categories VALUES (?, ?, ?)", (name, color, track))
            con.execute("INSERT OR IGNORE INTO settings VALUES ('tolerance_minutes', '10')")

    @staticmethod
    def _as_event(row: sqlite3.Row) -> Event:
        return Event(**{name: row[name] for name in Event.__dataclass_fields__})

    def categories(self) -> list[dict]:
        with self._connect() as con:
            return [dict(r) for r in con.execute("SELECT * FROM categories ORDER BY name")]

    def add_category(self, name: str, track: bool = True) -> None:
        name = name.strip()
        if not name or len(name) > 60:
            raise ValueError("Название категории должно содержать 1–60 символов")
        with self._connect() as con:
            con.execute("INSERT INTO categories VALUES (?, ?, ?)", (name, "#6A8DB8", int(track)))

    def set_category_tracking(self, name: str, track: bool) -> None:
        with self._connect() as con:
            con.execute("UPDATE categories SET track=? WHERE name=?", (int(track), name))

    def get_setting(self, key: str, default: str = "") -> str:
        with self._connect() as con:
            row = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self._connect() as con:
            con.execute("INSERT INTO settings VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

    @staticmethod
    def _audit(con: sqlite3.Connection, event_id: int | None, title: str, action: str, details: dict) -> None:
        con.execute(
            "INSERT INTO audit(event_id, title, action, details, changed_at) VALUES (?, ?, ?, ?, ?)",
            (event_id, title, action, json.dumps(details, ensure_ascii=False), now_iso()),
        )

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

    def get_event(self, event_id: int) -> Event:
        with self._connect() as con:
            r = con.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
        if r is None:
            raise KeyError(f"Мероприятие #{event_id} не найдено")
        return self._as_event(r)

    def update_event(self, event_id: int, **updates: str | None) -> None:
        allowed = {"title", "category", "current_start", "current_end", "actual_start", "actual_end", "status", "note"}
        if not updates or not set(updates).issubset(allowed):
            raise ValueError("Недопустимые поля изменения")
        old = self.get_event(event_id)
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
            self._audit(con, event_id, str(data["title"]), "Изменение", changes)

    def delete_event(self, event_id: int) -> None:
        ev = self.get_event(event_id)
        if ev.baseline_start is not None:
            raise ValueError("Мероприятие входит в зафиксированный план. Вместо удаления укажи статус «Отменено».")
        with self._connect() as con:
            con.execute("DELETE FROM events WHERE id=?", (event_id,))
            self._audit(con, event_id, ev.title, "Удаление", {"current_start": ev.current_start})

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
                self._audit(con, row["id"], row["title"], "Фиксация плана", {"day": day})
            return len(ids)

    def is_frozen(self, day: str) -> bool:
        with self._connect() as con:
            return con.execute("SELECT 1 FROM day_freezes WHERE day=?", (day,)).fetchone() is not None

    def daily_events(self, day: str) -> list[Event]:
        date.fromisoformat(day)
        with self._connect() as con:
            rows = con.execute("""
                SELECT * FROM events WHERE substr(current_start,1,10)=? OR substr(baseline_start,1,10)=?
                ORDER BY CASE WHEN substr(current_start,1,10)=? THEN current_start ELSE baseline_start END, id
            """, (day, day, day)).fetchall()
            return [self._as_event(r) for r in rows]

    def coverage_for_day(self, day: str, start_hour: int = 7, end_hour: int = 19) -> dict:
        """Find uncovered intervals and simultaneous events in the CURRENT day schedule."""
        date.fromisoformat(day)
        day_start = datetime.fromisoformat(f"{day}T{start_hour:02}:00:00")
        day_end = datetime.fromisoformat(f"{day}T{end_hour:02}:00:00")
        slots = []
        for event in self.daily_events(day):
            if event.current_start[:10] != day or event.status in {"cancelled", "moved"}:
                continue
            start = max(day_start, datetime.fromisoformat(event.current_start))
            end = min(day_end, datetime.fromisoformat(event.current_end))
            if start < end:
                slots.append((start, end))
        slots.sort()
        gaps = []
        cursor = day_start
        overlaps = 0
        for start, end in slots:
            if start > cursor:
                gaps.append((cursor.strftime("%H:%M"), start.strftime("%H:%M")))
            elif start < cursor:
                overlaps += 1
            cursor = max(cursor, end)
        if cursor < day_end:
            gaps.append((cursor.strftime("%H:%M"), day_end.strftime("%H:%M")))
        return {"gaps": gaps, "overlaps": overlaps}

    def day_summary(self, day: str) -> dict:
        with self._connect() as con:
            rows = con.execute("""
                SELECT e.*, c.track FROM events e JOIN categories c ON e.category=c.name
                WHERE substr(e.current_start,1,10)=? OR substr(e.baseline_start,1,10)=?
            """, (day, day)).fetchall()
        planned = [r for r in rows if r["baseline_start"] and r["baseline_start"][:10] == day and r["track"]]
        uncontrolled = [r for r in rows if r["track"] == 0]
        unscheduled = [r for r in rows if r["track"] and (not r["baseline_start"] or r["baseline_start"][:10] != day)
                       and r["current_start"][:10] == day]
        done = sum(r["status"] == "done" for r in planned)
        return {
            "total": len(rows), "planned": len(planned), "done": done,
            "partial": sum(r["status"] == "partial" for r in planned),
            "cancelled": sum(r["status"] == "cancelled" for r in planned),
            "moved": sum(r["status"] == "moved" for r in planned),
            "pending": sum(r["status"] == "pending" for r in planned),
            "unplanned": len(unscheduled), "nontracked": len(uncontrolled),
            "percent": (done / len(planned) * 100) if planned else None,
        }

    def category_totals(self, day: str) -> list[tuple[str, int, int]]:
        totals: dict[str, list[int]] = {}
        for ev in self.daily_events(day):
            planned, fact = totals.setdefault(ev.category, [0, 0])
            if ev.baseline_start and ev.baseline_start[:10] == day:
                planned += minutes_between(ev.baseline_start, ev.baseline_end)
            if ev.actual_start and ev.actual_start[:10] == day and ev.status in {"done", "partial"}:
                fact += minutes_between(ev.actual_start, ev.actual_end)
            totals[ev.category] = [planned, fact]
        return sorted(((name, pair[0], pair[1]) for name, pair in totals.items()), key=lambda x: -x[1])

    def audit_log(self, limit: int = 300) -> list[dict]:
        with self._connect() as con:
            return [dict(r) for r in con.execute("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,))]

    def export_csv(self, day: str, destination: Path | str) -> None:
        fields = ["id", "title", "category", "baseline_start", "baseline_end", "current_start", "current_end",
                  "actual_start", "actual_end", "status", "note", "source"]
        with open(destination, "w", encoding="utf-8-sig", newline="") as out:
            writer = csv.writer(out, delimiter=";")
            writer.writerow(["ID", "Мероприятие", "Категория", "Первоначально с", "Первоначально до", "Актуально с",
                             "Актуально до", "Факт с", "Факт до", "Статус", "Комментарий", "Источник"])
            for event in self.daily_events(day):
                values = asdict(event)
                values["status"] = STATUSES[values["status"]]
                # Protect Excel from interpreting attacker-supplied calendar text as formulas.
                def excel_safe(value):
                    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
                        return "'" + value
                    return value or ""
                writer.writerow([excel_safe(values[f]) for f in fields])

    def backup(self) -> Path:
        folder = self.path.parent / "backups"
        folder.mkdir(exist_ok=True)
        dest = folder / f"backup-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.db"
        with sqlite3.connect(self.path) as src, sqlite3.connect(dest) as dst:
            src.backup(dst)
        return dest

    def seed_demo(self, day: str) -> None:
        if self.daily_events(day) or self.is_frozen(day):
            raise ValueError("Демо-данные можно добавить только на пустую дату без зафиксированного плана")
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
        ids = []
        for title, cat, start, end in samples:
            ids.append(self.create_event(title, cat, f"{day}T{start}:00", f"{day}T{end}:00"))
        self.freeze_day(day)
        self.update_event(ids[0], status="done", actual_start=f"{day}T07:00:00", actual_end=f"{day}T08:00:00")
        self.update_event(ids[2], status="done", actual_start=f"{day}T09:00:00", actual_end=f"{day}T10:20:00", note="Совещание завершилось позднее")
        self.update_event(ids[3], status="partial", actual_start=f"{day}T10:20:00", actual_end=f"{day}T11:30:00")
        self.update_event(ids[4], status="done", actual_start=f"{day}T11:30:00", actual_end=f"{day}T12:30:00")
        self.update_event(ids[8], status="moved", note="Перенос на следующий день (демо)")
        self.update_event(ids[10], status="cancelled", note="Решение руководителя (демо)")
