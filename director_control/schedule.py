"""Shared, Qt-independent rules for selecting schedule layers."""
from datetime import datetime


def event_interval(event, layer):
    fields = {"current": ("current_start", "current_end"), "baseline": ("baseline_start", "baseline_end"),
              "actual": ("actual_start", "actual_end")}[layer]
    start, end = (getattr(event, field) for field in fields)
    if layer == "current" and event.source == "local" and not start:
        start, end = event.actual_start, event.actual_end
    return (datetime.fromisoformat(start), datetime.fromisoformat(end)) if start and end else None


def events_in_layer(events, layer, start, end):
    """Select half-open interval overlaps and order by the chosen layer's time."""
    selected = []
    for event in events:
        span = event_interval(event, layer)
        if span and span[0] < end and span[1] > start:
            selected.append((span[0], event.id, event))
    return [event for _, _, event in sorted(selected, key=lambda item: item[:2])]
