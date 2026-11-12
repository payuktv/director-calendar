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
from zoneinfo import ZoneInfo

from .provenance import work_origin
from .record_validation import (
    validate_calendar_window, validate_event_content, validate_remote_event, validate_text,
)
from .source_state import source_state

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


class EventConflictError(ValueError):
    """The editor's snapshot is no longer the current record."""


@dataclass(frozen=True)
class Event:
    id: int
    title: str
    category: str
    current_start: str | None
    current_end: str | None
    baseline_start: str | None
    baseline_end: str | None
    actual_start: str | None
    actual_end: str | None
    status: str
    note: str
    source: str
    revision: int = 0

    @property
    def is_postfactum(self) -> bool:
        return self.source == "local" and self.current_start is None

    @property
    def source_label(self) -> str:
        return "Локально" if self.source == "local" else "Mail.ru"


class Store:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path is not None else default_data_dir() / "director_control.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()
        from .legacy_cleanup import remove_legacy_examples
        remove_legacy_examples(self)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        from .database_guard import configure_connection
        con = sqlite3.connect(self.path, timeout=10)
        con.row_factory = sqlite3.Row
        try:
            configure_connection(con)
            con.execute("PRAGMA foreign_keys=ON")
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def _initialize(self) -> None:
        with self._connect() as con:
            if con.execute("PRAGMA user_version").fetchone()[0] > 4:
                raise ValueError("База создана более новой версией программы. Обнови приложение.")
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
                    current_start TEXT,
                    current_end TEXT,
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
                CREATE INDEX IF NOT EXISTS idx_audit_event ON audit(event_id,id DESC);
                CREATE INDEX IF NOT EXISTS idx_audit_changed ON audit(changed_at,id DESC);
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS calendar_events (
                    event_id INTEGER PRIMARY KEY REFERENCES events(id) ON DELETE CASCADE,
                    calendar_key TEXT NOT NULL,
                    uid TEXT NOT NULL,
                    recurrence_id TEXT NOT NULL,
                    missing INTEGER NOT NULL DEFAULT 0,
                    cancelled INTEGER NOT NULL DEFAULT 0,
                    all_day INTEGER NOT NULL DEFAULT 0,
                    baseline_all_day INTEGER,
                    local_status INTEGER NOT NULL DEFAULT 0
                );
            """)
            for name, color, track in DEFAULT_CATEGORIES:
                con.execute("INSERT OR IGNORE INTO categories VALUES (?, ?, ?)", (name, color, track))
            con.execute("INSERT OR IGNORE INTO settings VALUES ('tolerance_minutes', '10')")

        copied = self._migrate_local_events()
        self._migrate_reliability(copied)

    def _migrate_reliability(self, copied):
        with self._connect() as con:
            version = con.execute('PRAGMA user_version').fetchone()[0]
        if version == 4:
            return
        with self._connect() as con:
            has_data = con.execute('SELECT 1 FROM events LIMIT 1').fetchone() is not None
        if (version > 0 or has_data) and not copied:
            self.backup()
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            con.execute('''CREATE TABLE IF NOT EXISTS baseline_rules (
                event_id INTEGER PRIMARY KEY REFERENCES events(id) ON DELETE CASCADE,
                category TEXT NOT NULL, track INTEGER NOT NULL CHECK(track IN (0,1)),
                tolerance_minutes INTEGER NOT NULL)''')
            con.execute('''CREATE TABLE IF NOT EXISTS calendar_syncs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, calendar_key TEXT NOT NULL,
                start TEXT NOT NULL, end TEXT NOT NULL, status TEXT NOT NULL, finished_at TEXT NOT NULL)''')
            if 'revision' not in {row['name'] for row in con.execute('PRAGMA table_info(events)')}:
                con.execute('ALTER TABLE events ADD COLUMN revision INTEGER NOT NULL DEFAULT 0')
            tolerance = int(con.execute("SELECT value FROM settings WHERE key='tolerance_minutes'").fetchone()[0])
            con.execute('''INSERT OR IGNORE INTO baseline_rules SELECT e.id,e.category,c.track,? FROM events e
                JOIN categories c ON c.name=e.category WHERE e.baseline_start IS NOT NULL''', (tolerance,))
            if con.execute('PRAGMA foreign_key_check').fetchall():
                raise ValueError('Не удалось обновить формат базы: нарушены связи записей.')
            con.execute('PRAGMA user_version=4')

    def _migrate_local_events(self):
        with self._connect() as con:
            needs_rebuild = any(row["name"] in {"current_start", "current_end"} and row["notnull"]
                                for row in con.execute("PRAGMA table_info(events)"))
        if not needs_rebuild:
            return False
        # Save the old database before changing its format. A failed copy stops migration.
        self.backup()
        with self._connect() as con:
            con.execute("PRAGMA foreign_keys=OFF")
            con.execute("BEGIN IMMEDIATE")
            try:
                schema = con.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='events'").fetchone()[0]
                schema = schema.replace("current_start TEXT NOT NULL", "current_start TEXT")
                schema = schema.replace("current_end TEXT NOT NULL", "current_end TEXT")
                # Use the existing definition, including its foreign keys and constraints.
                opening = schema.index("(")
                con.execute("CREATE TABLE events_v3 " + schema[opening:])
                if any(row["name"] in {"current_start", "current_end"} and row["notnull"]
                       for row in con.execute("PRAGMA table_info(events_v3)")):
                    raise ValueError("Не удалось обновить формат временных полей. Исходная база сохранена.")
                sequence = con.execute("SELECT seq FROM sqlite_sequence WHERE name='events'").fetchone()
                objects = con.execute("SELECT sql FROM sqlite_master WHERE tbl_name='events' AND type IN ('index','trigger') AND sql IS NOT NULL").fetchall()
                con.execute("INSERT INTO events_v3 SELECT * FROM events")
                con.execute("DROP TABLE events")
                con.execute("ALTER TABLE events_v3 RENAME TO events")
                for row in objects:
                    con.execute(row[0])
                if sequence:
                    if con.execute("SELECT 1 FROM sqlite_sequence WHERE name='events'").fetchone():
                        con.execute("UPDATE sqlite_sequence SET seq=max(seq,?) WHERE name='events'", (sequence[0],))
                    else:
                        con.execute("INSERT INTO sqlite_sequence(name,seq) VALUES ('events',?)", (sequence[0],))
                if con.execute("PRAGMA foreign_key_check").fetchall():
                    raise ValueError("Не удалось обновить формат базы: нарушены связи записей.")
                con.execute("PRAGMA user_version=3")
                con.commit()
            except Exception:
                con.rollback()
                raise
            finally:
                con.execute("PRAGMA foreign_keys=ON")
        return True

    @staticmethod
    def _as_event(row: sqlite3.Row) -> Event:
        return Event(**{name: row[name] for name in Event.__dataclass_fields__})

    def categories(self) -> list[dict]:
        with self._connect() as con:
            return [dict(r) for r in con.execute("SELECT * FROM categories ORDER BY name")]

    def add_category(self, name: str, track: bool = True) -> None:
        try:
            validate_text(name)
        except ValueError:
            raise ValueError("Недопустимое название категории") from None
        name = name.strip()
        if not name or len(name) > 60:
            raise ValueError("Название категории должно содержать 1–60 символов")
        if type(track) not in (bool, int) or track not in (0, 1):
            raise ValueError("Укажи, контролировать ли категорию")
        with self._connect() as con:
            con.execute("INSERT INTO categories VALUES (?, ?, ?)", (name, "#6A8DB8", int(track)))
            self._audit(con, None, name, 'Создание категории', {'контролировать': bool(track)})

    def set_category_tracking(self, name: str, track: bool) -> None:
        if type(track) not in (bool, int) or track not in (0, 1):
            raise ValueError("Укажи, контролировать ли категорию")
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            old = con.execute('SELECT track FROM categories WHERE name=?', (name,)).fetchone()
            if old is None:
                raise ValueError('Категория не найдена')
            if old['track'] == int(track):
                return
            con.execute("UPDATE categories SET track=? WHERE name=?", (int(track), name))
            self._audit(con, None, name, 'Контроль категории', {'было': bool(old['track']), 'стало': bool(track)})

    def get_setting(self, key: str, default: str = "") -> str:
        with self._connect() as con:
            row = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self._connect() as con:
            if key == 'tolerance_minutes':
                if not 0 <= int(value) <= 180:
                    raise ValueError('Допустимое отклонение: от 0 до 180 минут')
                con.execute('BEGIN IMMEDIATE')
                old = con.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
                if old is None or old['value'] != value:
                    self._audit(con, None, 'Допустимое отклонение', 'Настройка контроля времени',
                                {'было': old['value'] if old else None, 'стало': value})
            con.execute("INSERT INTO settings VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

    @staticmethod
    def _audit(con: sqlite3.Connection, event_id: int | None, title: str, action: str, details: dict) -> None:
        con.execute(
            "INSERT INTO audit(event_id, title, action, details, changed_at) VALUES (?, ?, ?, ?, ?)",
            (event_id, title, action, json.dumps(details, ensure_ascii=False), now_iso()),
        )

    def get_event(self, event_id: int) -> Event:
        with self._connect() as con:
            r = con.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
        if r is None:
            raise KeyError(f"Мероприятие #{event_id} не найдено")
        return self._as_event(r)

    def _validate_event_data(self, data: dict) -> None:
        title = data.get("title")
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 200:
            raise ValueError("Название мероприятия должно содержать 1–200 символов")
        if data.get("status") not in STATUSES:
            raise ValueError("Неизвестный статус")
        if data.get("category") not in {row["name"] for row in self.categories()}:
            raise ValueError("Выбери существующую категорию")
        for start, end, label in (("current_start", "current_end", "Актуальный план"),
                                  ("actual_start", "actual_end", "Фактическое время")):
            if bool(data.get(start)) != bool(data.get(end)):
                raise ValueError(f"{label}: укажи оба времени либо оставь оба пустыми")
            if data.get(start):
                try:
                    stamps = [datetime.fromisoformat(data[field]) for field in (start, end)]
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"{label}: неверный формат даты/времени") from exc
                if any(stamp.tzinfo is not None for stamp in stamps):
                    raise ValueError(f"{label}: укажи местное время без часового пояса")
                validate_interval(data[start], data[end], label)
                data[start], data[end] = (stamp.isoformat() for stamp in stamps)
            else:
                data[start] = data[end] = None
        if not data.get("current_start") and not data.get("actual_start"):
            raise ValueError("Укажи фактическое время внепланового события или интервал плана")
        try:
            validate_event_content(data)
        except ValueError:
            raise ValueError("Некорректные данные события. Проверь название, примечание и время.") from None

    def create_event(self, title: str, category: str, current_start: str | None = None,
                     current_end: str | None = None, *, actual_start: str | None = None,
                     actual_end: str | None = None, status: str | None = None, note: str = "") -> int:
        """Create an app-only event; actual-only records can never enter the baseline."""
        data = dict(title=title.strip() if isinstance(title, str) else title, category=category, current_start=current_start,
                    current_end=current_end, actual_start=actual_start, actual_end=actual_end,
                    status=status if status is not None else ("pending" if current_start else "done"), note=(note or "").strip())
        self._validate_event_data(data)
        with self._connect() as con:
            cur = con.execute("""INSERT INTO events
                (title,category,current_start,current_end,actual_start,actual_end,status,note,source,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,'local',?,?)""",
                [data[key] for key in ("title", "category", "current_start", "current_end", "actual_start", "actual_end", "status", "note")]
                + [now_iso(), now_iso()])
            event_id = cur.lastrowid
            self._audit(con, event_id, data["title"], "Создание локального события", data)
            return event_id

    def _checked_event(self, con, event_id, expected_revision):
        row = con.execute('SELECT * FROM events WHERE id=?', (event_id,)).fetchone()
        if row is None:
            if expected_revision is not None:
                raise EventConflictError('Событие уже удалено. Закрой карточку и обнови календарь.')
            raise KeyError('Событие не найдено')
        event = self._as_event(row)
        if expected_revision is not None and event.revision != expected_revision:
            raise EventConflictError('Событие изменилось после открытия карточки. Изменения не сохранены. Закрой карточку и открой её снова.')
        return event

    def update_event(self, event_id: int, *, expected_revision=None, **updates: str | None) -> None:
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            self._update_event(con, event_id, expected_revision, updates)

    def _update_event(self, con, event_id, expected_revision, updates):
        old = self._checked_event(con, event_id, expected_revision)
        if old.source not in {"caldav", "local"}:
            raise ValueError("Учёт доступен для событий Mail.ru и новых локальных событий.")
        source_fields = {"title", "current_start", "current_end"}
        if old.source == "caldav" and source_fields.intersection(updates):
            raise ValueError("Название и плановое время события меняются только в Mail.ru.")
        allowed = {"category", "actual_start", "actual_end", "status", "note"}
        if old.source == "local":
            allowed |= source_fields
        if not updates or not set(updates).issubset(allowed):
            raise ValueError("Недопустимые поля изменения")
        data = asdict(old)
        data.update(updates)
        if "title" in updates and isinstance(data["title"], str):
            data["title"] = data["title"].strip()
        if "note" in updates:
            data["note"] = (data["note"] or "").strip()
        self._validate_event_data(data)
        if old.source == "local" and bool(old.current_start) != bool(data["current_start"]):
            raise ValueError("Тип существующего локального события менять нельзя: сохрани план и факт раздельно.")
        changes = {k: {"было": getattr(old, k), "стало": data[k]} for k in updates if getattr(old, k) != data[k]}
        if not changes:
            return
        columns = [f"{k}=?" for k in changes]
        con.execute(f"UPDATE events SET {', '.join(columns)}, revision=revision+1, updated_at=? WHERE id=?",
                    [data[k] for k in changes] + [now_iso(), event_id])
        if "status" in changes or "actual_start" in changes or "actual_end" in changes:
            con.execute("UPDATE calendar_events SET local_status=1 WHERE event_id=?", (event_id,))
        self._audit(con, event_id, str(data["title"]), "Изменение", changes)

    def delete_event(self, event_id: int, *, expected_revision=None) -> None:
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            event = self._checked_event(con, event_id, expected_revision)
            if event.source != "local":
                raise ValueError("Удалять можно только локальные события. События Mail.ru меняются в Mail.ru.")
            if event.baseline_start:
                raise ValueError("Событие входит в зафиксированный план. Вместо удаления выбери статус «Отменено».")
            self._audit(con, event_id, event.title, "Удаление локального события", asdict(event))
            con.execute("DELETE FROM events WHERE id=?", (event_id,))

    def freeze_day(self, day: str) -> int:
        day = date.fromisoformat(day).isoformat()
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            if con.execute("SELECT 1 FROM day_freezes WHERE day=?", (day,)).fetchone():
                raise ValueError("Первоначальный план на эту дату уже зафиксирован")
            con.execute("INSERT INTO day_freezes VALUES (?, ?)", (day, now_iso()))
            ids = con.execute("SELECT id, title FROM events WHERE source IN ('caldav','local') AND substr(current_start,1,10)=? AND baseline_start IS NULL", (day,)).fetchall()
            con.execute("""UPDATE events SET baseline_start=current_start, baseline_end=current_end, revision=revision+1
                        WHERE source IN ('caldav','local') AND substr(current_start,1,10)=? AND baseline_start IS NULL""", (day,))
            for row in ids:
                con.execute("UPDATE calendar_events SET baseline_all_day=all_day WHERE event_id=?", (row["id"],))
                con.execute('''INSERT INTO baseline_rules
                    SELECT e.id,e.category,c.track,CAST(s.value AS INTEGER) FROM events e
                    JOIN categories c ON c.name=e.category JOIN settings s ON s.key='tolerance_minutes'
                    WHERE e.id=?''', (row['id'],))
            for row in ids:
                self._audit(con, row["id"], row["title"], "Фиксация плана", {"day": day})
            return len(ids)

    def is_frozen(self, day: str) -> bool:
        with self._connect() as con:
            return con.execute("SELECT 1 FROM day_freezes WHERE day=?", (day,)).fetchone() is not None

    def baseline_rules(self):
        with self._connect() as con:
            return {row['event_id']: dict(row) for row in con.execute('SELECT * FROM baseline_rules')}

    def daily_events(self, day: str) -> list[Event]:
        date.fromisoformat(day)
        start = f"{day}T00:00:00"
        end = (date.fromisoformat(day) + timedelta(days=1)).isoformat() + "T00:00:00"
        return self.events_between(start, end)

    def events_between(self, start: str, end: str) -> list[Event]:
        """Include any current, baseline or actual interval overlapping [start, end)."""
        validate_interval(start, end)
        with self._connect() as con:
            rows = con.execute("""SELECT * FROM events
                WHERE source IN ('caldav','local') AND ((current_start<? AND current_end>?) OR (baseline_start<? AND baseline_end>?)
                OR (actual_start<? AND actual_end>?)) ORDER BY coalesce(current_start,actual_start), id""",
                (end, start, end, start, end, start)).fetchall()
            return [self._as_event(row) for row in rows]

    def coverage_for_day(self, day: str, start_hour: int = 7, end_hour: int = 19) -> dict:
        """Find uncovered intervals and simultaneous events in the CURRENT day schedule."""
        date.fromisoformat(day)
        day_start = datetime.fromisoformat(f"{day}T{start_hour:02}:00:00")
        day_end = datetime.fromisoformat(f"{day}T{end_hour:02}:00:00")
        slots = []
        metadata = self.calendar_info()
        for event in self.daily_events(day):
            if (not event.current_start or event.status in {"cancelled", "moved"}
                    or metadata.get(event.id, {}).get("all_day")):
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
        start = f"{day}T00:00:00"
        end = (date.fromisoformat(day) + timedelta(days=1)).isoformat() + "T00:00:00"
        with self._connect() as con:
            con.execute('BEGIN')
            frozen = {r['day'] for r in con.execute('SELECT day FROM day_freezes')}
            rows = con.execute("""
                SELECT e.*, c.track, coalesce(b.track,c.track) AS baseline_track FROM events e
                JOIN categories c ON e.category=c.name LEFT JOIN baseline_rules b ON b.event_id=e.id
                WHERE e.source IN ('caldav','local') AND ((e.current_start<? AND e.current_end>?) OR (e.baseline_start<? AND e.baseline_end>?) OR (e.actual_start<? AND e.actual_end>?))
            """, (end, start, end, start, end, start)).fetchall()
        planned = [r for r in rows if r["baseline_start"] and r["baseline_start"][:10] == day and r["baseline_track"]]
        uncontrolled = [r for r in rows if not r['baseline_track']]
        origins = [work_origin(self._as_event(r), frozen) for r in rows if r['baseline_track']]
        unscheduled = origins.count('unplanned')
        done = sum(r["status"] == "done" for r in planned)
        return {
            "total": len(rows), "planned": len(planned), "done": done,
            "partial": sum(r["status"] == "partial" for r in planned),
            "cancelled": sum(r["status"] == "cancelled" for r in planned),
            "moved": sum(r["status"] == "moved" for r in planned),
            "pending": sum(r["status"] == "pending" for r in planned),
            "unplanned": unscheduled, "unfixed": origins.count("unfixed"), "nontracked": len(uncontrolled),
            "percent": (done / len(planned) * 100) if planned else None,
        }

    def category_totals(self, day: str) -> list[tuple[str, int, int]]:
        totals: dict[str, list[int]] = {}
        metadata = self.calendar_info()
        rules = self.baseline_rules()
        start = f"{day}T00:00:00"
        end = (date.fromisoformat(day) + timedelta(days=1)).isoformat() + "T00:00:00"
        for ev in self.daily_events(day):
            totals.setdefault(ev.category, [0, 0])
            if ev.baseline_start and not metadata.get(ev.id, {}).get("baseline_all_day"):
                category = rules.get(ev.id, {}).get('category', ev.category)
                totals.setdefault(category, [0, 0])[0] += max(0, minutes_between(max(start, ev.baseline_start), min(end, ev.baseline_end)))
            if ev.actual_start and ev.status in {"done", "partial"}:
                totals[ev.category][1] += max(0, minutes_between(max(start, ev.actual_start), min(end, ev.actual_end)))
        return sorted(((name, pair[0], pair[1]) for name, pair in totals.items()), key=lambda x: -x[1])

    def analytics_report(self, anchor: date | str, mode: str = 'week', only_tracked: bool = True):
        from .analytics import build_report, period_bounds
        from .mail_calendar import CalendarConfig
        anchor = date.fromisoformat(anchor) if isinstance(anchor, str) else anchor
        start, end = period_bounds(anchor, mode)
        begin, finish = start.isoformat() + 'T00:00:00', end.isoformat() + 'T00:00:00'
        with self._connect() as con:
            # One read transaction: no mixed revisions if a sync commits during the report.
            con.execute('BEGIN')
            events = [self._as_event(r) for r in con.execute('''SELECT * FROM events
                WHERE source IN ('caldav','local') AND ((baseline_start<? AND baseline_end>?)
                OR (current_start<? AND current_end>?) OR (actual_start<? AND actual_end>?))
                ORDER BY coalesce(actual_start,baseline_start,current_start),id''',
                (finish, begin, finish, begin, finish, begin))]
            categories = [dict(r) for r in con.execute('SELECT * FROM categories')]
            rules = {r['event_id']: dict(r) for r in con.execute('SELECT * FROM baseline_rules')}
            metadata = {r['event_id']: dict(r) for r in con.execute('SELECT * FROM calendar_events')}
            frozen = {r['day'] for r in con.execute('SELECT day FROM day_freezes')}
            syncs = [dict(r) for r in con.execute('SELECT * FROM calendar_syncs')]
            settings = dict(con.execute('SELECT key,value FROM settings'))
        key = CalendarConfig(settings['mail_url'], settings.get('mail_login', '')).calendar_key if settings.get('mail_url') else None
        return build_report(anchor, mode, only_tracked, events, categories, rules, metadata, frozen, syncs, key)

    def audit_log(self, limit: int = 300) -> list[dict]:
        with self._connect() as con:
            return [dict(r) for r in con.execute("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,))]

    def audit_page(self, *, search='', date_from=None, date_to=None, event_id=None,
                   event_search='', before_id=None, ceiling_id=None, limit=100):
        """Read a filtered, ID-ordered page. Dates are inclusive change dates.

        A fixed ceiling prevents inserts from shifting older pages. No OFFSET or
        journal truncation is used. Raw audit records remain available to callers.
        """
        from .history import AuditPage, matches, normalise
        if not isinstance(limit, int) or not 1 <= limit <= 500:
            raise ValueError('Размер страницы: от 1 до 500 записей.')
        if any(value is not None and (not isinstance(value, int) or value < 0)
               for value in (before_id, ceiling_id)):
            raise ValueError('Некорректная граница страницы истории.')
        start = date.fromisoformat(date_from) if isinstance(date_from, str) else date_from
        end = date.fromisoformat(date_to) if isinstance(date_to, str) else date_to
        if start and end and start > end:
            raise ValueError('Дата «С» должна быть не позже даты «По».')
        clauses, args = [], []
        if start:
            clauses.append('a.changed_at>=?')
            args.append(start.isoformat() + 'T00:00:00')
        if end:
            clauses.append('a.changed_at<?')
            args.append((end + timedelta(days=1)).isoformat() + 'T00:00:00')
        if event_id == 'system':
            clauses.append('a.event_id IS NULL')
        elif event_id is not None:
            if not isinstance(event_id, int) or event_id <= 0:
                raise ValueError('Выбери событие из истории.')
            clauses.append('a.event_id=?')
            args.append(event_id)
        if normalise(event_search):
            clauses.append('''a.event_id IN (SELECT b.event_id FROM audit b
                WHERE b.event_id IS NOT NULL AND instr(history_fold(b.title),?)>0)''')
            args.append(normalise(event_search))
        if normalise(search):
            clauses.append('history_matches(a.title,a.action,a.details,a.changed_at,?)')
            args.append(search)
        filters = ''.join(' AND ' + clause for clause in clauses)
        with self._connect() as con:
            con.create_function('history_fold', 1, normalise, deterministic=True)
            con.create_function('history_matches', 5, matches, deterministic=True)
            con.execute('BEGIN')
            maximum = con.execute('SELECT coalesce(max(id),0) FROM audit').fetchone()[0]
            ceiling = maximum if ceiling_id is None else ceiling_id
            total = con.execute('SELECT count(*) FROM audit a WHERE a.id<=?' + filters, [ceiling, *args]).fetchone()[0]
            newer = con.execute('SELECT count(*) FROM audit a WHERE a.id>?' + filters, [ceiling, *args]).fetchone()[0] if maximum > ceiling else 0
            boundary = ' AND a.id<?' if before_id is not None else ''
            rows = con.execute('SELECT a.* FROM audit a WHERE a.id<=?' + filters + boundary + ' ORDER BY a.id DESC LIMIT ?',
                               [ceiling, *args, *([before_id] if before_id is not None else []), limit + 1]).fetchall()
        return AuditPage(tuple(dict(row) for row in rows[:limit]), total, ceiling, len(rows) > limit, newer)

    def audit_event_options(self):
        """Include deleted and archived events, identified by ID rather than title."""
        with self._connect() as con:
            return [dict(row) for row in con.execute('''SELECT a.event_id,
                coalesce(e.title,a.title) AS title, e.id IS NULL AS deleted, e.source,
                coalesce(e.current_start,e.baseline_start,e.actual_start) AS starts
                FROM audit a JOIN (SELECT event_id,max(id) AS latest FROM audit
                WHERE event_id IS NOT NULL GROUP BY event_id) last ON a.id=last.latest
                LEFT JOIN events e ON e.id=a.event_id ORDER BY a.id DESC''')]

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
                values["source"] = event.source_label
                # Protect Excel from interpreting attacker-supplied calendar text as formulas.
                def excel_safe(value):
                    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
                        return "'" + value
                    return value or ""
                writer.writerow([excel_safe(values[f]) for f in fields])

    def backup(self) -> Path:
        from .backups import create_backup
        return create_backup(self)

    def calendar_info(self) -> dict[int, dict]:
        with self._connect() as con:
            return {r["event_id"]: dict(r) for r in con.execute("SELECT * FROM calendar_events")}

    def record_sync_failure(self, calendar_key, start, end):
        def stamp(value):
            value = value.isoformat() if isinstance(value, date) else value
            return value + 'T00:00:00' if len(value) == 10 else value
        start, end = stamp(start), stamp(end)
        validate_calendar_window(calendar_key, start, end)
        with self._connect() as con:
            con.execute("INSERT INTO calendar_syncs(calendar_key,start,end,status,finished_at) VALUES (?,?,?,'failed',?)",
                        (calendar_key, start, end, now_iso()))

    def sync_warning(self, day, calendar_key):
        start = day + 'T00:00:00'
        end = (date.fromisoformat(day) + timedelta(days=1)).isoformat() + 'T00:00:00'
        with self._connect() as con:
            row = con.execute("""SELECT * FROM calendar_syncs WHERE calendar_key=?
                AND start<=? AND end>=? ORDER BY id DESC LIMIT 1""",
                (calendar_key, start, end)).fetchone()
        if row is None:
            return 'Нет подтверждённого полного обновления Mail.ru за выбранный день.'
        if row['status'] != 'complete':
            return ('Последнее обновление Mail.ru за этот день было частичным.' if row['status'] == 'partial'
                    else 'Последняя попытка обновить Mail.ru за этот день завершилась ошибкой.')
        age = datetime.now() - datetime.fromisoformat(row['finished_at'])
        if age < timedelta(0) or age > timedelta(minutes=30):
            return 'Данные Mail.ru за этот день обновлялись более 30 минут назад. Расписание могло измениться.'
        return ''

    def has_schedule_events(self) -> bool:
        with self._connect() as con:
            return con.execute("SELECT 1 FROM events WHERE source IN ('caldav','local') LIMIT 1").fetchone() is not None

    def apply_calendar_snapshot(self, snapshot) -> dict[str, int]:
        """Atomically upsert source data; baseline, local fact, category and notes survive."""
        stats = {"added": 0, "updated": 0, "missing": 0, "withdrawn": 0}
        seen = set()
        # Validate before starting; on any failure the transaction also rolls back.
        try:
            validate_calendar_window(snapshot.calendar_key, snapshot.start, snapshot.end)
            for event in snapshot.events:
                validate_remote_event(event)
        except ValueError:
            raise ValueError("Некорректные данные календаря. Данные не изменены.") from None
        for event in snapshot.events:
            if event.key in seen:
                raise ValueError("Повторный идентификатор события в ответе календаря")
            seen.add(event.key)
        with self._connect() as con:
            con.execute('BEGIN IMMEDIATE')
            zone = con.execute("SELECT value FROM settings WHERE key='mail_timezone'").fetchone()
            calendar_today = datetime.now(ZoneInfo(zone[0] if zone else 'Europe/Moscow')).date().isoformat()
            con.execute("INSERT OR IGNORE INTO categories VALUES ('Mail.ru', '#55A7D9', 1)")
            con.execute("INSERT OR IGNORE INTO categories VALUES ('Весь день (Mail.ru)', '#8B9EA4', 0)")
            for event in snapshot.events:
                row = con.execute("SELECT * FROM events WHERE external_key=?", (event.key,)).fetchone()
                source_status = "cancelled" if event.cancelled else "pending"
                if row is None:
                    cur = con.execute("""INSERT INTO events
                        (title, category, current_start, current_end, status, source, external_key, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, 'caldav', ?, ?, ?)""",
                        (event.title, "Весь день (Mail.ru)" if event.all_day else "Mail.ru", event.start, event.end,
                         source_status, event.key, now_iso(), now_iso()))
                    event_id = cur.lastrowid
                    con.execute("""INSERT INTO calendar_events
                        (event_id, calendar_key, uid, recurrence_id, cancelled, all_day) VALUES (?, ?, ?, ?, ?, ?)""",
                        (event_id, snapshot.calendar_key, event.uid, event.recurrence_id,
                         int(event.cancelled), int(event.all_day)))
                    self._audit(con, event_id, event.title, "Импорт Mail.ru", {"start": event.start, "end": event.end})
                    stats["added"] += 1
                else:
                    event_id = row["id"]
                    meta = con.execute("SELECT * FROM calendar_events WHERE event_id=?", (event_id,)).fetchone()
                    if row["source"] != "caldav" or meta is None or meta["calendar_key"] != snapshot.calendar_key:
                        raise ValueError("Конфликт источника календаря")
                    status = row["status"] if meta["local_status"] else source_status
                    changes = {k: {"было": row[k], "стало": v} for k, v in {
                        "title": event.title, "current_start": event.start, "current_end": event.end,
                        "status": status,
                    }.items() if row[k] != v}
                    if meta["missing"] or meta["cancelled"] != int(event.cancelled) or meta["all_day"] != int(event.all_day):
                        changes["источник"] = {"missing": False, "cancelled": event.cancelled, "all_day": event.all_day}
                    if changes:
                        con.execute("""UPDATE events SET title=?, current_start=?, current_end=?, status=?, revision=revision+1, updated_at=?
                            WHERE id=?""", (event.title, event.start, event.end, status, now_iso(), event_id))
                        self._audit(con, event_id, event.title, "Обновление Mail.ru", changes)
                        stats["updated"] += 1
                    con.execute("UPDATE calendar_events SET missing=0, cancelled=?, all_day=? WHERE event_id=?",
                                (int(event.cancelled), int(event.all_day), event_id))
            # Absence in a bounded query does not prove deletion (e.g. moved outside the window).
            rows = con.execute("""SELECT e.*, m.missing, m.local_status FROM events e
                JOIN calendar_events m ON m.event_id=e.id WHERE m.calendar_key=?
                AND e.current_start>=? AND e.current_start<?""",
                (snapshot.calendar_key, snapshot.start, snapshot.end)).fetchall() if snapshot.complete else []
            for row in rows:
                if row["external_key"] not in seen:
                    frozen = con.execute('''SELECT 1 FROM day_freezes
                        WHERE day>=substr(?,1,10) AND day || 'T00:00:00'<? LIMIT 1''',
                        (row['current_start'], row['current_end'])).fetchone()
                    if (row['source'] == 'caldav' and row['current_start'][:10] >= calendar_today
                            and not frozen and not row['baseline_start'] and not row['baseline_end']
                            and not row['actual_start'] and not row['actual_end']
                            and not row['local_status'] and row['status'] in ('pending', 'cancelled')
                            and not row['note']):
                        # Retain identity and audit; a later source response restores this row.
                        con.execute('''UPDATE events SET current_start=NULL, current_end=NULL,
                            revision=revision+1, updated_at=? WHERE id=?''', (now_iso(), row['id']))
                        con.execute('UPDATE calendar_events SET missing=1 WHERE event_id=?', (row['id'],))
                        self._audit(con, row['id'], row['title'], 'Убрано из актуального плана Mail.ru', {
                            'current_start': {'было': row['current_start'], 'стало': None},
                            'current_end': {'было': row['current_end'], 'стало': None}})
                        stats['withdrawn'] += 1
                        continue
                    if row['missing']:
                        continue
                    con.execute("UPDATE calendar_events SET missing=1 WHERE event_id=?", (row["id"],))
                    con.execute('UPDATE events SET revision=revision+1 WHERE id=?', (row['id'],))
                    state = source_state(self._as_event(row), {'missing': 1})
                    action = ('Отменённое событие отсутствует в Mail.ru' if state.code == 'cancelled_missing'
                              else 'Нет в ответе Mail.ru')
                    self._audit(con, row["id"], row["title"], action, {"требует проверки": state.needs_review})
                    stats["missing"] += 1
            sync_key = "mail_last_sync" if snapshot.complete else "mail_last_partial"
            con.execute("INSERT INTO calendar_syncs(calendar_key,start,end,status,finished_at) VALUES (?,?,?,?,?)",
                        (snapshot.calendar_key, snapshot.start, snapshot.end,
                         'complete' if snapshot.complete else 'partial', now_iso()))
            con.execute("INSERT INTO settings VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                        (sync_key, now_iso()))
            review_rows = con.execute("""SELECT e.*,m.missing,m.cancelled,m.local_status FROM events e
                JOIN calendar_events m ON e.id=m.event_id WHERE m.calendar_key=?
                AND (m.missing=1 OR m.cancelled=1) AND (e.current_start IS NOT NULL
                OR e.baseline_start IS NOT NULL OR e.actual_start IS NOT NULL)""",
                (snapshot.calendar_key,)).fetchall()
            stats['missing'] = sum(source_state(self._as_event(row), dict(row)).needs_review for row in review_rows)
        return stats


