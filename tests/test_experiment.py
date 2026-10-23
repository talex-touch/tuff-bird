"""Reading a log directory back: its runs, their scalars, and how runs share a curve."""

from __future__ import annotations

import pytest
from helpers import logged_run, quiet_run

import tuffbird
from tuffbird import BY_DIRECTORY
from tuffbird.experiment import PALETTE, as_tags, hex_color

POINTS = [(0, 4.0), (1, 2.0), (2, 1.0)]


@pytest.fixture
def sweep(tmp_path):
    """Two directories of seeds and a run at the top. Created in name order, so start time and name agree."""
    logged_run(tmp_path, "seed-1", POINTS, group="ppo", config={"algo": "ppo", "lr": 0.0003})
    logged_run(tmp_path, "seed-2", POINTS, group="sac", config={"algo": "sac", "lr": 0.001})
    logged_run(tmp_path, "seed-10", POINTS, group="sac", config={"algo": "sac", "lr": 0.001})
    logged_run(tmp_path, "solo", POINTS)
    return tuffbird.load(tmp_path)


def layout(curves):
    return [(curve.key, curve.label, curve.color, list(curve.runs)) for curve in curves]


def test_load_needs_an_existing_directory(tmp_path):
    with pytest.raises(FileNotFoundError, match="no log directory"):
        tuffbird.load(tmp_path / "missing")


def test_tags_sort_as_the_board_lists_them(tmp_path):
    run = quiet_run(tmp_path, "run")
    run.log({"layer10/loss": 1.0, "layer2/loss": 1.0, "Eval/return": 1.0}, step=0)
    run.finish()
    assert tuffbird.load(tmp_path).tags == ["Eval/return", "layer2/loss", "layer10/loss"]


def test_scalars_and_running_follow_what_the_runs_wrote(tmp_path):
    logged_run(tmp_path, "done", [(0, 1.0), (1, 0.5)])
    live = quiet_run(tmp_path, "live")
    live.log({"loss": 2.0}, step=0)
    live.flush()

    experiment = tuffbird.load(tmp_path)
    assert experiment.running
    assert experiment.scalars("loss") == {"done": [(0, 1.0), (1, 0.5)], "live": [(0, 2.0)]}
    assert experiment.scalars("missing") == {}
    live.finish()
    assert not experiment.refresh().running


def test_runs_list_each_run_with_its_directory_and_config(sweep):
    runs = {run.id: run for run in sweep.runs}
    assert list(runs) == ["ppo/seed-1", "sac/seed-2", "sac/seed-10", "solo"]
    assert (runs["sac/seed-10"].name, runs["sac/seed-10"].parent, runs["sac/seed-10"].status) == ("seed-10", "sac", "finished")
    assert runs["sac/seed-10"].hparams == {"algo": "sac", "lr": 0.001}
    assert runs["solo"].parent == ""


def test_by_default_the_runs_in_a_directory_share_a_curve_in_the_boards_colors(sweep):
    assert layout(sweep.curves("loss")) == [
        ("group:ppo", "ppo", PALETTE[0], ["ppo/seed-1"]),
        ("group:sac", "sac", PALETTE[1], ["sac/seed-2", "sac/seed-10"]),
        ("solo", "solo", PALETTE[3], ["solo"]),
    ]
    assert sweep.curves("loss", BY_DIRECTORY)[1].seeds == [POINTS, POINTS]


def test_group_by_none_draws_every_run_on_its_own(sweep):
    assert layout(sweep.curves("loss", group_by=None)) == [
        ("ppo/seed-1", "ppo/seed-1", PALETTE[0], ["ppo/seed-1"]),
        ("sac/seed-2", "sac/seed-2", PALETTE[1], ["sac/seed-2"]),
        ("sac/seed-10", "sac/seed-10", PALETTE[2], ["sac/seed-10"]),
        ("solo", "solo", PALETTE[3], ["solo"]),
    ]


def test_a_config_key_groups_runs_by_value_in_numeric_order(sweep):
    # As text, "lr=0.001" would come first; runs without the key stay on their own, after the groups.
    assert layout(sweep.curves("loss", group_by="lr")) == [
        ("by:lr=0.0003", "lr=0.0003", PALETTE[0], ["ppo/seed-1"]),
        ("by:lr=0.001", "lr=0.001", PALETTE[1], ["sac/seed-2", "sac/seed-10"]),
        ("solo", "solo", PALETTE[2], ["solo"]),
    ]


def test_several_config_keys_combine_into_one_label(sweep):
    labels = [curve.label for curve in sweep.curves("loss", group_by=["algo", "lr"])]
    assert labels == ["algo=ppo, lr=0.0003", "algo=sac, lr=0.001", "solo"]


def test_a_function_labels_each_run_or_leaves_it_alone(sweep):
    curves = sweep.curves("loss", group_by=lambda run: run.parent.upper() or None)
    assert [(curve.label, list(curve.runs)) for curve in curves] == [
        ("PPO", ["ppo/seed-1"]),
        ("SAC", ["sac/seed-2", "sac/seed-10"]),
        ("solo", ["solo"]),
    ]


@pytest.mark.parametrize("group_by", [3, [], ["lr", 1]])
def test_group_by_rejects_what_it_cannot_group_by(sweep, group_by):
    with pytest.raises(TypeError, match="group_by takes"):
        sweep.curves("loss", group_by=group_by)


def test_check_tags_names_the_tags_no_run_logged(sweep):
    assert sweep.check_tags("loss") == ["loss"]
    with pytest.raises(ValueError, match=r"logged accuracy; its tags: loss"):
        sweep.check_tags(["loss", "accuracy"])
    with pytest.raises(ValueError, match="at least one tag"):
        as_tags([])


def test_hex_color_drops_the_css_variable():
    assert hex_color(PALETTE[0]) == "#4290f0"
    assert hex_color("#2f9e44") == "#2f9e44"
