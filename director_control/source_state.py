"""One interpretation of source presence and local execution status."""
from dataclasses import dataclass


@dataclass(frozen=True)
class SourceState:
    code: str
    suffix: str = ''
    warning: str = ''

    @property
    def needs_review(self):
        return bool(self.warning)


def source_state(event, metadata):
    """Absence is expected for a cancelled event; retain all records and facts.

    ``missing`` is set only by a complete bounded query. It describes source
    presence, not whether the retained local record is an unresolved problem.
    """
    if not metadata:
        return SourceState('local' if event.source == 'local' else 'present')
    if metadata.get('missing'):
        if event.status == 'cancelled':
            return SourceState('cancelled_missing', 'нет в Mail.ru')
        return SourceState('missing', 'проверить Mail.ru', 'Не найдено в Mail.ru')
    if metadata.get('cancelled'):
        if event.status != 'cancelled':
            return SourceState('source_cancelled_conflict', 'отменено в Mail.ru', 'Отменено в Mail.ru')
        return SourceState('cancelled_in_source')
    if event.status == 'cancelled' and metadata.get('local_status'):
        return SourceState('cancelled_locally', 'есть в Mail.ru')
    return SourceState('present')
