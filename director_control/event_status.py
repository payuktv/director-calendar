"""Execution statuses shared by storage, validation and presentation."""

from .i18n import tr

STATUSES = {
    "pending": "Не подтверждено",
    "done": "Выполнено",
    "partial": "Частично",
    "cancelled": "Отменено",
    "moved": "Перенесено",
    "failed_assistant": "Провалено · ассистент",
    "failed_director": "Провалено · директор",
}
FAILED_STATUSES = frozenset({"failed_assistant", "failed_director"})


def fill_completed_actual(data, *, all_day=False):
    """Fill only an entirely absent fact on an explicit completion write.

    Use the current advertised interval, not an earlier frozen plan. A partial
    pair must reach validation unchanged; a supplied fact always takes priority.
    """
    if data["status"] != "done" or all_day or data.get("actual_start") or data.get("actual_end"):
        return
    start = data.get("current_start") or data.get("baseline_start")
    end = data.get("current_end") or data.get("baseline_end")
    if start and end:
        data.update(actual_start=start, actual_end=end)


def outcome_day(event):
    """Count cancellations/failures once, on the original plan's date if any."""
    return (event.baseline_start or event.current_start or event.actual_start or "")[:10]


def status_hint(status):
    if status == "done":
        return tr("Если факт не указан, при сохранении он заполнится по текущему времени события. Его можно изменить. События на весь день — без автозаполнения.")
    if status == "partial":
        return tr("Укажи фактическое время. Пока оно не заполнено, событие будет ожидать его в аналитике (кроме событий на весь день).")
    if status in FAILED_STATUSES:
        return tr("Событие не состоялось из-за указанного участника. Оно учитывается отдельно от отмен и не добавляет часы работы. Причину можно записать в примечании.")
    return tr("Фактическое время учитывается в аналитике для статусов «Выполнено» и «Частично».")
