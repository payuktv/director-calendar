"""Readable audit entries. The original journal is never rewritten."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache

from .i18n import current_language, tr
from .storage import STATUSES, category_label

ACTION_LABELS = {
    'Создание': 'Создано событие',
    'Создание локального события': 'Создано локальное событие',
    'Удаление локального события': 'Удалено локальное событие',
    'Изменение': 'Изменены данные события',
    'Импорт Mail.ru': 'Загружено из Mail.ru',
    'Обновление Mail.ru': 'Обновлено из Mail.ru',
    'Нет в ответе Mail.ru': 'Нужна проверка в Mail.ru',
    'Отменённое событие отсутствует в Mail.ru': 'Отмена согласована с источником',
    'Фиксация плана': 'Зафиксирован исходный план',
    'Создание категории': 'Добавлена категория',
    'Контроль категории': 'Изменён контроль категории',
    'Настройка контроля времени': 'Изменён допуск времени',
    'Настройки копирования': 'Изменены настройки копий',
    'Восстановление из копии': 'Восстановлена база данных',
    'Очистка старых примеров': 'Удалены старые примеры',
    'Убрано из актуального плана Mail.ru': 'Убрано из актуального плана Mail.ru',
    'Проваленное событие отсутствует в Mail.ru': 'Проваленное событие отсутствует в Mail.ru',
}
FIELD_LABELS = {
    'title': 'Название', 'category': 'Категория', 'status': 'Статус', 'note': 'Комментарий',
    'current_start': 'Начало актуального плана', 'current_end': 'Окончание актуального плана',
    'baseline_start': 'Начало исходного плана', 'baseline_end': 'Окончание исходного плана',
    'actual_start': 'Фактическое начало', 'actual_end': 'Фактическое окончание',
    'start': 'Начало расписания', 'end': 'Окончание расписания', 'day': 'Дата плана',
    'source': 'Источник', 'missing': 'Отсутствует в ответе Mail.ru', 'cancelled': 'Отменено в Mail.ru',
    'all_day': 'Событие на весь день', 'baseline_all_day': 'Исходный план на весь день',
    'backup_auto': 'Ежедневные резервные копии', 'backup_folder': 'Папка резервных копий',
    'backup_keep': 'Хранить автоматических копий', 'tolerance_minutes': 'Допустимое отклонение',
    'контролировать': 'Участие категории в контроле', 'удалено': 'Удалено старых примеров',
    'копия': 'Использованная копия', 'страховая копия': 'Страховая копия перед восстановлением',
    'требует проверки': 'требует проверки',
}
HIDDEN_FIELDS = {'id', 'event_id', 'revision', 'created_at', 'updated_at', 'external_key'}
SOURCES = {'local': 'Локально в приложении', 'caldav': 'Mail.ru', 'manual': 'Архив приложения'}


def normalise(value: str) -> str:
    """Unicode case folding, including the usual е/ё spelling variants."""
    return ' '.join(str(value).casefold().replace('ё', 'е').split())


def display_time(value, *, seconds=False):
    if not value:
        return tr('не заполнено')
    try:
        stamp = datetime.fromisoformat(str(value))
        if len(str(value)) == 10:
            return stamp.strftime('%d.%m.%Y')
        return stamp.strftime('%d.%m.%Y %H:%M:%S' if seconds or stamp.second or stamp.microsecond else '%d.%m.%Y %H:%M')
    except (ValueError, TypeError):
        return str(value)


def _value(field, value):
    if value is None:
        return tr('не заполнено')
    if field == 'status':
        return tr(STATUSES[str(value)]) if str(value) in STATUSES else str(value)
    if field == 'source':
        return tr(SOURCES[str(value)]) if str(value) in SOURCES else str(value)
    if field == 'category':
        return category_label(str(value))
    if field in {'backup_auto', 'контролировать', 'track'}:
        return tr('включено') if value in (True, 1, '1') else tr('выключено')
    if field == 'backup_folder' and not value:
        return tr('папка по умолчанию')
    if field in {'current_start', 'current_end', 'baseline_start', 'baseline_end', 'actual_start', 'actual_end', 'start', 'end', 'day'}:
        return display_time(value)
    if field == 'tolerance_minutes':
        return str(value) + tr(' мин')
    if isinstance(value, bool):
        return tr('да') if value else tr('нет')
    if isinstance(value, list):
        return '; '.join(_value('', item) for item in value) or tr('нет данных')
    if isinstance(value, dict):
        return '; '.join(_lines(value)) or tr('нет данных')
    return str(value) if str(value) else tr('не заполнено')


def _lines(data):
    lines = []
    for field, value in data.items():
        if field in HIDDEN_FIELDS:
            continue
        if field == 'источник' and isinstance(value, dict):
            lines.append(tr('Состояние в Mail.ru:'))
            lines.extend('  ' + line for line in _lines(value))
            continue
        # Known old-format fields remain readable; future fields keep their values.
        label = tr(FIELD_LABELS[field]) if field in FIELD_LABELS else (
            field if any('а' <= c.lower() <= 'я' or c.lower() == 'ё' for c in field) else tr('Дополнительные данные'))
        if isinstance(value, dict) and ('было' in value or 'стало' in value):
            lines.append(f'{label}: {_value(field, value.get("было"))} → {_value(field, value.get("стало"))}')
        else:
            lines.append(f'{label}: {_value(field, value)}')
    return lines


@dataclass(frozen=True)
class Description:
    action: str
    details: str


def describe(action: str, raw: str) -> Description:
    return _describe(action, raw, current_language())


@lru_cache(maxsize=4096)
def _describe(action: str, raw: str, language: str) -> Description:
    label = tr(ACTION_LABELS[action]) if action in ACTION_LABELS else action
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return Description(label, tr('Описание прежнего формата:\n') + str(raw) if raw else tr('Подробности не сохранены'))
    if not isinstance(data, dict):
        return Description(label, _value('', data))
    if action == 'Контроль категории':
        data = {'контролировать': data}
    elif action == 'Настройка контроля времени':
        data = {'tolerance_minutes': data}
    elif action == 'Нет в ответе Mail.ru':
        return Description(label, tr('Событие не найдено в загруженном периоде Mail.ru. Проверь источник: это не подтверждает удаление события.'))
    elif action == 'Отменённое событие отсутствует в Mail.ru':
        return Description(label, tr('Событие отменено и отсутствует в полностью загруженном периоде Mail.ru. '
                           'План, локальные данные и история сохранены. Дополнительная проверка не требуется.'))
    lines = _lines(data)
    return Description(label, '\n'.join(lines) if lines else tr('Подробности не сохранены'))


def matches(title, action, raw, changed_at, query):
    description = describe(action, raw)
    document = normalise(' '.join((title, history_title(title, action), action, description.action, description.details,
                                  changed_at, display_time(changed_at, seconds=True))))
    return all(term in document for term in normalise(query).split())


def history_title(title, action):
    if action in ('Контроль категории', 'Создание категории'):
        return category_label(title)
    if action in ('Настройки копирования', 'Восстановление из копии', 'Настройка контроля времени', 'Очистка старых примеров'):
        return tr(title)
    return title


@dataclass(frozen=True)
class AuditPage:
    rows: tuple[dict, ...]
    total: int
    ceiling_id: int
    has_older: bool
    newer_count: int
