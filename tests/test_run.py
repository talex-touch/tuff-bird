"""What a training script leaves on disk."""

from __future__ import annotations

import os
import subprocess
import sys

import pytest
from helpers import quiet_run, read_events, values_of

from tuffrl.events import HParamsEnd, HParamsStart, Scalar, Text


def test_run_writes_metrics_config_and_end(tmp_path):
    run = quiet_run(tmp_path, "seed-0", group="sweep/lr-0.5", config={"lr": 0.5, "net": {"width": 64}, "opt": "adam"})
    run.log({"train": {"loss": 0.5}, "note": "not a number"}, step=3)
    run.log({"train/loss": 0.25})
    run.log_text("notes", "hello")
    run.finish()

    events = read_events(tmp_path, "sweep/lr-0.5/seed-0")
    [start] = values_of(events, HParamsStart)
    assert start.hparams == {"lr": 0.5, "net/width": 64, "opt": "adam"}
    assert start.group == "sweep/lr-0.5"
    scalars = [(event.step, value.tag, value.value) for event in events for value in event.values if isinstance(value, Scalar)]
    assert scalars == [(3, "train/loss", 0.5), (4, "train/loss", 0.25)]
    assert [value.text for value in values_of(events, Text)] == ["hello"]
    assert [value.status for value in values_of(events, HParamsEnd)] == ["success"]


def test_finish_twice_writes_one_end(tmp_path):
    run = quiet_run(tmp_path, "once")
    run.finish("failure")
    run.finish()
    assert [value.status for value in values_of(read_events(tmp_path, "once"), HParamsEnd)] == ["failure"]


@pytest.mark.parametrize(("raised", "status"), [("RuntimeError", "failure"), ("KeyboardInterrupt", "unknown")])
def test_a_script_that_dies_records_why(tmp_path, raised, status):
    script = (
        "import tuffrl\n"
        f"tuffrl.init(logdir={str(tmp_path)!r}, name='run', board=False, system_metrics=False)\n"
        "print('before the end')\n"
        f"raise {raised}('boom')\n"
    )
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, env={**os.environ, "TUFFRL_BOARD": "0"})
    assert result.returncode != 0

    events = read_events(tmp_path, "run")
    assert [value.status for value in values_of(events, HParamsEnd)] == [status]
    output = {}
    for value in values_of(events, Text):
        output[value.tag] = output.get(value.tag, "") + value.text
    assert "before the end" in output["stdout"]
    assert f"{raised}: boom" in output["stderr"]
