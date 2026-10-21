"""Small helpers shared by the tests."""

from __future__ import annotations

from tuffrl import Run
from tuffrl.events import Event, RunReader, discover_runs


def quiet_run(logdir, name, **options) -> Run:
    """A run that writes only what the test logs: no board, no captured output, no system metrics."""
    return Run(logdir=str(logdir), name=name, board=False, capture_output=False, system_metrics=False, **options)


def read_events(logdir, run_id: str) -> list[Event]:
    return RunReader(discover_runs(str(logdir))[run_id]).poll()


def values_of(events: list[Event], kind: type) -> list:
    return [value for event in events for value in event.values if isinstance(value, kind)]
