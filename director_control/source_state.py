"""One interpretation of source presence and local execution status."""
from dataclasses import dataclass

from .i18n import tr
from .event_status import FAILED_STATUSES


@dataclass(frozen=True)
class SourceState:
    code: str
    suffix: str = ''
    warning: str = ''

    @property
    def needs_review(self):
        return bool(self.warning)


def source_state(event, metadata):
    """Absence is expected for a cancelled/failed event; retain records and facts.

    ``missing`` is set only by a complete bounded query. It describes source
    presence, not whether the retained local record is an unresolved problem.
    """
    if not metadata:
        return SourceState('local' if event.source == 'local' else 'present')
    if metadata.get('missing'):
        if event.status == 'cancelled':
            return SourceState('cancelled_missing', tr('нет в Mail.ru'))
        if event.status in FAILED_STATUSES:
            return SourceState('failed_missing', tr('нет в Mail.ru'))
        return SourceState('missing', tr('проверить Mail.ru'), tr('Не найдено в Mail.ru'))
    if metadata.get('cancelled'):
        if event.status in FAILED_STATUSES:
            return SourceState('failed_cancelled_in_source', tr('отменено в Mail.ru'))
        if event.status != 'cancelled':
            return SourceState('source_cancelled_conflict', tr('отменено в Mail.ru'), tr('Отменено в Mail.ru'))
        return SourceState('cancelled_in_source')
    if event.status == 'cancelled' and metadata.get('local_status'):
        return SourceState('cancelled_locally', tr('есть в Mail.ru'))
    if event.status in FAILED_STATUSES and metadata.get('local_status'):
        return SourceState('failed_locally', tr('есть в Mail.ru'))
    return SourceState('present')
