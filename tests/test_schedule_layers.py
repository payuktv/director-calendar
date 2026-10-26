from datetime import datetime

import pytest
from PySide6.QtCore import QDate
from PySide6.QtWidgets import QApplication

from director_control.schedule import events_in_layer
from director_control.storage import Store
from director_control.ui import MainWindow

DAY = '2026-10-26'


@pytest.mark.parametrize('mode', ['day', 'week', 'month', 'agenda'])
@pytest.mark.parametrize('layer', ['current', 'baseline', 'actual'])
def test_layers_use_the_same_events_in_grid_and_list(tmp_path, mode, layer):
    app = QApplication.instance() or QApplication([])
    store = Store(tmp_path / 'layers.db')
    planned = store.create_event('Исходный план', 'Работа', DAY+'T09:00:00', DAY+'T10:00:00')
    store.freeze_day(DAY)
    extra = store.create_event('Новый план', 'Работа', DAY+'T12:00:00', DAY+'T13:00:00')
    fact = store.create_event('Постфактум', 'Работа', actual_start=DAY+'T11:00:00', actual_end=DAY+'T11:30:00')
    window = MainWindow(store)
    window.set_date(QDate(2026, 10, 26))
    window.set_view(mode)
    window._selected_id = fact
    window.layer.setCurrentIndex(window.layer.findData(layer))
    window.reload()
    expected = {'current': [planned, fact, extra], 'baseline': [planned], 'actual': [fact]}[layer]
    assert window.row_ids == expected
    assert {b.event.id for blocks in window.calendar.timed.values() for b in blocks} == set(expected)
    if layer == 'baseline':
        assert window.selected_event_id() is None
    window.close()
    app.processEvents()


def test_cross_midnight_layer_selection_uses_exclusive_end(tmp_path):
    store = Store(tmp_path / 'midnight.db')
    eid = store.create_event('Ночной факт', 'Работа', actual_start=DAY+'T23:30:00', actual_end='2026-10-27T00:00:00')
    events = [store.get_event(eid)]
    assert events_in_layer(events, 'actual', datetime(2026, 10, 26), datetime(2026, 10, 27)) == events
    assert events_in_layer(events, 'actual', datetime(2026, 10, 27), datetime(2026, 10, 28)) == []
