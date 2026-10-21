"""The board's view of a log directory: runs, their status, and what changed since a point."""

from __future__ import annotations

import os
import time

import pytest
from helpers import quiet_run

from tuffrl.board.store import IDLE_AFTER_SECS, Store
from tuffrl.events import discover_runs


def finished_run(logdir, name, status):
    run = quiet_run(logdir, name)
    for step in range(3):
        run.log({"loss": float(step)}, step=step)
    run.finish(status)


def test_status_comes_from_the_end_record_or_the_last_write(tmp_path):
    finished_run(tmp_path, "done", "success")
    finished_run(tmp_path, "crashed", "failure")
    finished_run(tmp_path, "interrupted", "unknown")
    live = quiet_run(tmp_path, "live")
    live.log({"loss": 1.0}, step=0)
    live.flush()
    quiet = quiet_run(tmp_path, "quiet")
    quiet.flush()
    old = time.time() - IDLE_AFTER_SECS - 5
    for path in discover_runs(str(tmp_path))["quiet"]:
        os.utime(path, (old, old))

    store = Store(str(tmp_path))
    store.scan()
    status = {run["id"]: run["status"] for run in store.snapshot()["runs"]}
    assert status == {"crashed": "failed", "done": "finished", "interrupted": "stopped", "live": "running", "quiet": "idle"}
    live.finish()
    quiet.finish()


def test_deltas_carry_only_new_points(tmp_path):
    run = quiet_run(tmp_path, "run")
    run.log({"loss": 0.5}, step=0)
    run.flush()
    store = Store(str(tmp_path))
    store.scan()
    snapshot = store.snapshot()
    assert [point[:2] for point in snapshot["scalars"]["run"]["loss"]] == [[0, 0.5]]

    run.log({"loss": 0.25}, step=1)
    run.flush()
    store.scan()
    deltas = store.wait_deltas(snapshot["seq"], timeout=0)
    points = [delta["points"] for delta in deltas if delta["type"] == "scalars"]
    assert [[point[:2] for point in batch] for batch in points] == [[[1, 0.25]]]
    assert all(delta["seq"] > snapshot["seq"] for delta in deltas)
    run.finish()


@pytest.mark.parametrize("ahead", [1, 100])
def test_a_position_from_another_board_cannot_be_resumed(tmp_path, ahead):
    finished_run(tmp_path, "run", "success")
    store = Store(str(tmp_path))
    store.scan()
    assert store.wait_deltas(store.seq + ahead, timeout=0) is None
    assert store.wait_deltas(store.seq, timeout=0) == []
