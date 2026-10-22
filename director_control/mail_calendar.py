"""Read-only CalDAV transport and iCalendar expansion. Never writes to the server."""
from __future__ import annotations

import hashlib
import posixpath
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from time import monotonic
from urllib.parse import unquote, urljoin, urlsplit
from xml.etree.ElementTree import Element, SubElement, tostring
from zoneinfo import ZoneInfo

import recurring_ical_events
import requests
from defusedxml.ElementTree import fromstring
from icalendar import Calendar

DAV = "DAV:"
CALDAV = "urn:ietf:params:xml:ns:caldav"
MAX_BYTES = 16 * 1024 * 1024
MAX_OCCURRENCES = 20000
MAX_FALLBACK_GETS = 50


def _status_code(value: str) -> int | None:
    """Parse the numeric status; the HTTP reason phrase may be absent."""
    parts = value.split()
    if len(parts) >= 2 and parts[0].startswith("HTTP/") and parts[1].isdigit():
        code = int(parts[1])
        if 100 <= code <= 599:
            return code
    return None


class CalendarError(Exception):
    """A user-safe error without response bodies, secrets or private calendar data."""


@dataclass(frozen=True)
class CalendarConfig:
    url: str
    username: str
    timezone: str = "Europe/Moscow"

    def validate(self) -> None:
        p = urlsplit(self.url)
        if (p.scheme != "https" or p.hostname != "calendar.mail.ru" or p.port not in (None, 443)
                or p.username or p.password or p.query or p.fragment or not p.path.endswith("/")):
            raise CalendarError("Укажи HTTPS-ссылку CalDAV с calendar.mail.ru, без параметров и с / в конце.")
        if not self.username.strip() or "@" not in self.username:
            raise CalendarError("Укажи полный адрес почты для входа.")
        try:
            ZoneInfo(self.timezone)
        except (ValueError, KeyError):
            raise CalendarError("Неизвестный часовой пояс.") from None

    @property
    def calendar_key(self) -> str:
        # Account is part of identity: switching credentials must not mix calendar copies.
        return hashlib.sha256((self.url + "\n" + self.username.lower()).encode()).hexdigest()


@dataclass(frozen=True)
class RemoteEvent:
    key: str
    uid: str
    recurrence_id: str
    title: str
    start: str
    end: str
    cancelled: bool = False
    all_day: bool = False


@dataclass(frozen=True)
class CalendarSnapshot:
    calendar_key: str
    start: str
    end: str
    events: tuple[RemoteEvent, ...]
    unavailable: tuple[str, ...] = ()

    @property
    def complete(self) -> bool:
        return not self.unavailable


def _resource_url(config: CalendarConfig, href: str) -> str | None:
    """Only authenticate GETs to child resources of the selected collection."""
    if not href or any(ord(char) < 32 or char == "\\" for char in href):
        return None
    try:
        target = urljoin(config.url, href)
        parts = urlsplit(target)
        if (parts.scheme != "https" or parts.hostname != "calendar.mail.ru" or parts.port not in (None, 443)
                or parts.username or parts.password or parts.query or parts.fragment):
            return None
        path = unquote(parts.path)
        # Reject double escaping and decoded separators that could change server routing.
        if "%" in path or "\\" in path or any(ord(char) < 32 for char in path):
            return None
        collection = posixpath.normpath(unquote(urlsplit(config.url).path)) + "/"
        normalized = posixpath.normpath(path)
        if not normalized.startswith(collection) or path.endswith("/"):
            return None
        return target
    except ValueError:
        return None


def _read_limited(response, budget: dict) -> bytes:
    chunks = []
    for chunk in response.iter_content(65536):
        budget["bytes"] += len(chunk)
        if budget["bytes"] > MAX_BYTES:
            raise CalendarError("Ответ календаря слишком большой. Данные не изменены.")
        if monotonic() > budget["deadline"]:
            raise CalendarError("Превышено время загрузки календаря. Данные не изменены.")
        chunks.append(chunk)
    return b"".join(chunks)


def _fallback_get(session, config, password, href, budget):
    url = _resource_url(config, href)
    if url is None:
        return None, "адрес записи отсутствует или вне выбранного календаря"
    if budget["gets"] >= MAX_FALLBACK_GETS:
        return None, "достигнут лимит отдельных запросов"
    remaining = budget["deadline"] - monotonic()
    if remaining <= 0:
        raise CalendarError("Превышено время загрузки календаря. Данные не изменены.")
    budget["gets"] += 1
    with session.request("GET", url, headers={"Accept": "text/calendar"}, auth=(config.username, password),
                         timeout=(min(10, remaining), min(15, remaining)), allow_redirects=False,
                         stream=True) as response:
        if response.status_code != 200:
            return None, f"GET {response.status_code}"
        # Parse bytes through icalendar so UTF-8 is independent of HTTP's charset guess.
        body = _read_limited(response, budget)
        if not body.strip():
            return None, "пустой ответ GET"
        return body, ""


def window_for_day(day: date) -> tuple[date, date]:
    return day - timedelta(days=30), day + timedelta(days=91)


def _aware(value: date | datetime, zone: ZoneInfo) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=zone) if value.tzinfo is None else value.astimezone(zone)
    return datetime.combine(value, time.min, zone)


def _identity(value: date | datetime, zone: ZoneInfo) -> str:
    if not isinstance(value, datetime):
        return "date:" + value.isoformat()
    return _aware(value, zone).astimezone(UTC).isoformat(timespec="seconds")


def parse_calendars(blobs: list[str | bytes], config: CalendarConfig, start: date, end: date) -> CalendarSnapshot:
    """Parse the whole response before any database write. Bad series abort the snapshot."""
    config.validate()
    zone = ZoneInfo(config.timezone)
    lower, upper = _aware(start, zone), _aware(end, zone)
    if not lower < upper or (end - start).days > 366:
        raise CalendarError("Диапазон синхронизации должен быть от 1 до 366 дней.")
    merged = Calendar()
    merged.add("version", "2.0")
    components = {}
    series = set()
    try:
        for blob in blobs:
            cal = Calendar.from_ical(blob)
            if cal.name != "VCALENDAR":
                raise ValueError("Not a calendar")
            for component in cal.subcomponents:
                if component.name == "VTIMEZONE":
                    merged.add_component(component)
                elif component.name == "VEVENT":
                    uid = str(component.get("UID", ""))
                    if not uid or component.errors:
                        raise ValueError("Invalid event")
                    if any(field in component for field in ("RRULE", "RDATE", "RECURRENCE-ID")):
                        series.add(uid)
                    rid = component.decoded("RECURRENCE-ID", None)
                    identity = (uid, _identity(rid, zone) if rid else "single")
                    if identity in components and components[identity].to_ical() != component.to_ical():
                        raise ValueError("Conflicting duplicate UID")
                    components[identity] = component
        for component in components.values():
            rule = component.get("RRULE")
            if rule and str(rule.get("FREQ", [""])[0]).upper() in {"SECONDLY", "MINUTELY"}:
                raise CalendarError("Повторы каждую секунду или минуту пока не поддерживаются. Данные не изменены.")
            # A TZID silently falling back to naive local time is unsafe.
            for name in ("DTSTART", "DTEND", "RECURRENCE-ID"):
                prop = component.get(name)
                if prop is not None and prop.params.get("TZID"):
                    dt = prop.dt
                    if isinstance(dt, datetime) and dt.tzinfo is None:
                        raise ValueError("Unknown TZID")
            merged.add_component(component)
        occurrences = recurring_ical_events.of(merged, keep_recurrence_attributes=True).between(lower, upper)
        if len(occurrences) > MAX_OCCURRENCES:
            raise ValueError("Too many occurrences")
        events = {}
        for component in occurrences:
            uid = str(component["UID"])
            dtstart = component.decoded("DTSTART")
            dtend = component.decoded("DTEND", None)
            all_day = isinstance(dtstart, date) and not isinstance(dtstart, datetime)
            if dtend is None:
                duration = component.decoded("DURATION", None)
                if duration is None:
                    if not all_day:
                        raise ValueError("Timed event has no duration")
                    duration = timedelta(days=1)
                dtend = dtstart + duration
            begin, finish = _aware(dtstart, zone), _aware(dtend, zone)
            if finish <= begin:
                raise ValueError("Invalid interval")
            if begin >= upper or finish <= lower:
                continue
            rid = component.decoded("RECURRENCE-ID", dtstart) if uid in series else None
            recurrence_id = _identity(rid, zone) if rid is not None else "single"
            key = hashlib.sha256((config.calendar_key + "\n" + uid + "\n" + recurrence_id).encode()).hexdigest()
            events[key] = RemoteEvent(
                key=key, uid=uid, recurrence_id=recurrence_id,
                title=(str(component.get("SUMMARY", "Без названия")).strip() or "Без названия")[:200],
                start=begin.replace(tzinfo=None).isoformat(timespec="seconds"),
                end=finish.replace(tzinfo=None).isoformat(timespec="seconds"),
                cancelled=str(component.get("STATUS", "")).upper() == "CANCELLED", all_day=all_day,
            )
    except CalendarError:
        raise
    except Exception:
        raise CalendarError("Не удалось разобрать события календаря. Данные не изменены; проверь формат и часовые пояса.") from None
    return CalendarSnapshot(config.calendar_key, lower.replace(tzinfo=None).isoformat(timespec="seconds"),
                            upper.replace(tzinfo=None).isoformat(timespec="seconds"), tuple(events.values()))


def fetch_snapshot(config: CalendarConfig, password: str, start: date, end: date) -> CalendarSnapshot:
    config.validate()
    if not password:
        raise CalendarError("Введи пароль внешнего приложения.")
    zone = ZoneInfo(config.timezone)
    if start >= end or (end - start).days > 366:
        raise CalendarError("Недопустимый диапазон синхронизации.")
    query = Element(f"{{{CALDAV}}}calendar-query")
    prop = SubElement(query, f"{{{DAV}}}prop")
    SubElement(prop, f"{{{CALDAV}}}calendar-data")
    filtering = SubElement(query, f"{{{CALDAV}}}filter")
    outer = SubElement(filtering, f"{{{CALDAV}}}comp-filter", name="VCALENDAR")
    inner = SubElement(outer, f"{{{CALDAV}}}comp-filter", name="VEVENT")
    SubElement(inner, f"{{{CALDAV}}}time-range", {
        "start": _aware(start, zone).astimezone(UTC).strftime("%Y%m%dT%H%M%SZ"),
        "end": _aware(end, zone).astimezone(UTC).strftime("%Y%m%dT%H%M%SZ"),
    })
    budget = {"bytes": 0, "gets": 0, "deadline": monotonic() + 120}
    try:
        with requests.Session() as session:
            session.trust_env = False  # No ambient .netrc credentials or unexpected proxy credentials.
            with session.request("REPORT", config.url, data=tostring(query, encoding="utf-8", xml_declaration=True),
                                 headers={"Depth": "1", "Content-Type": "application/xml; charset=utf-8"},
                                 auth=(config.username, password), timeout=(10, 45), allow_redirects=False,
                                 stream=True) as response:
                if response.status_code in (401, 403):
                    raise CalendarError("Mail.ru отклонил доступ. Проверь логин, пароль приложения и права на календарь.")
                if response.status_code != 207:
                    raise CalendarError(f"Mail.ru вернул код {response.status_code}. Проверь ссылку и повтори позже.")
                body = _read_limited(response, budget)
            root = fromstring(body)
            if root.tag != f"{{{DAV}}}multistatus":
                raise CalendarError("Mail.ru вернул неожиданный формат. Данные не изменены.")
            blobs = []
            unavailable = []
            results = root.findall(f"{{{DAV}}}response")
            for index, result in enumerate(results, 1):
                direct_status = result.findtext(f"{{{DAV}}}status", "")
                if direct_status and _status_code(direct_status) != 200:
                    code = _status_code(direct_status)
                    raise CalendarError(f"CalDAV: ресурс {index}, HTTP {code or 'неизвестен'}. Данные не изменены.")
                values = []
                data_codes = []
                group_codes = []
                for group in result.findall(f"{{{DAV}}}propstat"):
                    code = _status_code(group.findtext(f"{{{DAV}}}status", ""))
                    group_codes.append(str(code) if code is not None else "неизвестен")
                    data = group.find(f"{{{DAV}}}prop/{{{CALDAV}}}calendar-data")
                    if data is not None:
                        data_codes.append(str(code) if code is not None else "неизвестен")
                        if code == 200 and data.text and data.text.strip():
                            values.append(data.text)
                    # Other property failures (e.g. getetag=404) do not invalidate calendar-data=200.
                if not values and data_codes and set(data_codes) == {"404"}:
                    recovered, reason = _fallback_get(session, config, password,
                                                      result.findtext(f"{{{DAV}}}href", ""), budget)
                    if recovered is not None:
                        values.append(recovered)
                    else:
                        unavailable.append(f"ресурс {index} из {len(results)}: calendar-data 404; {reason}")
                        continue
                if not values:
                    # Report only numeric statuses and ordinal positions, never hrefs, bodies or credentials.
                    detail = ", ".join(data_codes) if data_codes else "нет свойства; статусы: " + ", ".join(group_codes)
                    raise CalendarError(f"CalDAV: ресурс {index} из {len(results)}, calendar-data: {detail or 'нет статуса'}. "
                                        "Данные не изменены.")
                if any(value != values[0] for value in values[1:]):
                    raise CalendarError("CalDAV вернул противоречивые данные одного события. Данные не изменены.")
                blobs.append(values[0])
            if unavailable and not blobs:
                raise CalendarError("Не удалось прочитать ни одной записи. " + unavailable[0] + ". Данные не изменены.")
            snapshot = parse_calendars(blobs, config, start, end)
            return replace(snapshot, unavailable=tuple(unavailable))
    except CalendarError:
        raise
    except requests.exceptions.RequestException:
        raise CalendarError("Не удалось подключиться к Mail.ru. Проверь интернет; локальные данные сохранены.") from None
    except Exception:
        raise CalendarError("Не удалось прочитать ответ Mail.ru. Локальные данные не изменены.") from None
