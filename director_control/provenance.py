"""Shared origin of work, independent of the displayed date and status."""


def work_origin(event, frozen_days):
    """A baseline survives moves; an unfrozen day cannot prove unplanned work."""
    if event.baseline_start and event.baseline_end:
        return 'planned'
    if event.is_postfactum or (event.current_start and event.current_start[:10] in frozen_days):
        return 'unplanned'
    return 'unfixed'
