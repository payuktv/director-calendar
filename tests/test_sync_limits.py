"""Resource boundaries use synthetic calendars and small, bounded child processes."""
from datetime import date
import subprocess
import sys
from time import monotonic

import pytest

from director_control import mail_calendar, sync_process
from director_control.mail_calendar import CalendarError
from tests.test_mail_calendar import CONFIG, START, END, calendar, event, parse


def test_count_limit_stops_consumption_before_building_the_whole_result(monkeypatch):
    monkeypatch.setattr(mail_calendar, 'MAX_OCCURRENCES', 2)
    with pytest.raises(CalendarError, match='много повторов'):
        parse(event(extra='RRULE:FREQ=DAILY;COUNT=3'))
    assert len(parse(event(extra='RRULE:FREQ=DAILY;COUNT=2')).events) == 2


def test_generated_stream_is_not_consumed_past_limit(monkeypatch):
    from icalendar import Calendar
    component = Calendar.from_ical(calendar(event())).walk('VEVENT')[0]
    consumed = []

    class Query:
        def after(self, lower):
            for index in range(4):
                consumed.append(index)
                yield component
            raise AssertionError('Consumed beyond the limit')

    monkeypatch.setattr(mail_calendar.recurring_ical_events, 'of', lambda *a, **kw: Query())
    monkeypatch.setattr(mail_calendar, 'MAX_OCCURRENCES', 2)
    with pytest.raises(CalendarError, match='много повторов'):
        parse(event())
    assert consumed == [0, 1, 2]


def test_real_worker_preserves_recurrence_exceptions_and_identity():
    blobs = [calendar(event(extra='RRULE:FREQ=DAILY;COUNT=4\nEXDATE:20261023T090000Z'),
                      event(extra='RECURRENCE-ID:20261024T090000Z',
                            start='20261025T110000Z', end='20261025T120000Z'))]
    assert sync_process.parse_isolated(blobs, CONFIG, START, END) == mail_calendar.parse_calendars(blobs, CONFIG, START, END)


@pytest.mark.parametrize('items', [
    [event(extra='RRULE:FREQ=MONTHLY;BYDAY=MO,TU,WE,TH,FR;BYSETPOS=-1')],
    [event(extra='RDATE:20261023T090000Z,20261024T090000Z\nEXDATE:20261023T090000Z')],
    ['UID:overlap\nDTSTART:20261019T090000Z\nDTEND:20261023T090000Z\nRRULE:FREQ=WEEKLY;COUNT=3'],
    ['UID:all-day\nDTSTART;VALUE=DATE:20261020\nDTEND;VALUE=DATE:20261023\nRRULE:FREQ=DAILY;COUNT=8'],
    ['UID:dst\nDTSTART;TZID=Europe/Berlin:20261024T090000\nDTEND;TZID=Europe/Berlin:20261024T100000\nRRULE:FREQ=DAILY;COUNT=4'],
    [],
])
def test_stream_matches_previous_window_semantics(monkeypatch, items):
    actual = parse(*items)
    real_of = mail_calendar.recurring_ical_events.of
    class Reference:
        def __init__(self, *args, **kwargs):
            self.query = real_of(*args, **kwargs)
        def after(self, lower):
            return iter(sorted(self.query.between(lower, mail_calendar._aware(END, lower.tzinfo)),
                               key=lambda c: mail_calendar._aware(c.decoded('DTSTART'), lower.tzinfo)))
    monkeypatch.setattr(mail_calendar.recurring_ical_events, 'of', Reference)
    expected = parse(*items)
    assert {e.key: e for e in actual.events} == {e.key: e for e in expected.events}


def test_real_dense_hourly_rule_fails_without_returning_partial_snapshot():
    # HOURLY bypassed the previous SECONDLY/MINUTELY exclusion. This produces
    # >20,000 instances without asking the test host to exhaust its memory.
    dense = calendar(event(extra='RRULE:FREQ=HOURLY;BYMINUTE=' + ','.join(map(str, range(60)))))
    with pytest.raises(CalendarError):
        sync_process.parse_isolated([dense], CONFIG, START, date(2026, 11, 15), timeout=8)


@pytest.mark.parametrize('cancel', [False, True])
def test_timeout_or_cancellation_kills_and_reaps_child(monkeypatch, cancel):
    monkeypatch.setattr(sync_process, '_worker_command', lambda: [sys.executable, '-c', 'import time; time.sleep(30)'])
    real_popen = subprocess.Popen
    children = []
    def popen(*args, **kwargs):
        child = real_popen(*args, **kwargs)
        children.append(child)
        return child
    monkeypatch.setattr(sync_process.subprocess, 'Popen', popen)
    started = monotonic()
    with pytest.raises(CalendarError, match='отменено' if cancel else 'время'):
        sync_process._run_worker({}, cancelled=lambda: cancel and monotonic() - started > .2, timeout=.5)
    assert monotonic() - started < 5
    assert len(children) == 1 and children[0].poll() is not None
    assert children[0].stdin.closed and children[0].stdout.closed


def test_os_memory_limit_rejects_a_small_bounded_allocation():
    # Runs only in an isolated child; never stress the main process or the OS.
    script = ('from director_control.sync_process import limit_resources\n'
              'limit_resources(128*1024*1024)\n'
              'try:\n value=bytearray(160*1024*1024)\n'
              'except MemoryError:\n print("limited")\n')
    result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0 and result.stdout.strip() == 'limited', result.stderr


def test_failing_limit_setup_never_reaches_untrusted_parsing(monkeypatch):
    def fail():
        raise OSError('private')
    monkeypatch.setattr(sync_process, 'limit_resources', fail)
    assert sync_process.worker_main() == 1


def test_worker_does_not_open_database_or_log_calendar_content(tmp_path, monkeypatch):
    monkeypatch.setenv('DIRECTOR_CONTROL_DATA_DIR', str(tmp_path))
    result = sync_process.parse_isolated([calendar(event())], CONFIG, START, END)
    assert len(result.events) == 1 and not list(tmp_path.iterdir())


@pytest.mark.parametrize('close_window', [False, True])
def test_cancellation_discards_already_queued_success_and_closes_window(tmp_path, close_window):
    from PySide6.QtCore import QThread
    from PySide6.QtWidgets import QApplication
    from director_control.mail_ui import SyncThread
    from director_control.storage import Store
    from director_control.ui import MainWindow
    app = QApplication.instance() or QApplication([])
    store = Store(tmp_path/'gui.db')
    store.apply_calendar_snapshot(parse(event()))
    store.freeze_day('2026-10-22')
    original = store.daily_events('2026-10-22')[0]
    store.update_event(original.id, status='done', note='Preserve this',
                       actual_start=original.current_start, actual_end=original.current_end)
    saved = store.get_event(original.id)
    audit_count = len(store.audit_log())
    window = MainWindow(store)
    window.show()
    panel = window.mail_panel
    # An actual worker waits until interrupted, then tries to deliver late data.
    snapshot = parse(event(start='20261023T090000Z', end='20261023T100000Z'))
    class Waiting(SyncThread):
        def run(self):
            while not self.isInterruptionRequested():
                self.msleep(5)
            self.snapshot_ready.emit(snapshot)
    worker = Waiting(CONFIG, 'synthetic', date(2026, 10, 22), panel)
    panel.worker = worker
    panel.set_controls(False)
    worker.snapshot_ready.connect(panel.apply_snapshot)
    worker.finished.connect(panel.finished)
    worker.start()
    if close_window:
        window.close()
    else:
        panel.cancel_button.click()
    deadline = monotonic() + 5
    while panel.busy and monotonic() < deadline:
        app.processEvents()
        QThread.msleep(5)
    app.processEvents()
    assert not panel.busy and window.isVisible() != close_window
    assert store.get_event(original.id) == saved and len(store.audit_log()) == audit_count
    assert store.daily_events('2026-10-23') == []
    window.close()


def test_protocol_errors_are_private(monkeypatch):
    monkeypatch.setattr(sync_process, '_worker_command', lambda: [sys.executable, '-c',
        'import sys; print("PRIVATE-SERVER-BODY"); sys.exit(1)'])
    with pytest.raises(CalendarError) as exc:
        sync_process._run_worker({})
    assert 'PRIVATE' not in str(exc.value)
