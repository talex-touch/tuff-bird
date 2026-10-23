"""Small helpers shared by the tests."""

from __future__ import annotations

import json
import re

from tuffbird import Run
from tuffbird.events import Event, RunReader, discover_runs


def quiet_run(logdir, name, **options) -> Run:
    """A run that writes only what the test logs: no board, no captured output, no system metrics."""
    return Run(logdir=str(logdir), name=name, board=False, capture_output=False, system_metrics=False, **options)


def read_events(logdir, run_id: str) -> list[Event]:
    return RunReader(discover_runs(str(logdir))[run_id]).poll()


def values_of(events: list[Event], kind: type) -> list:
    return [value for event in events for value in event.values if isinstance(value, kind)]


def logged_run(logdir, name, points, *, tag="loss", **options) -> None:
    """A finished run that logged ``tag`` at each ``(step, value)``."""
    run = quiet_run(logdir, name, **options)
    for step, value in points:
        run.log({tag: value}, step=step)
    run.finish()


def spec_in(page: str) -> dict:
    """The chart's data inside a saved chart."""
    match = re.search(r'<script type="application/json" class="tuffbird-chart__spec">(.*?)</script>', page, re.S)
    assert match, "no chart in the page"
    return json.loads(match.group(1))
