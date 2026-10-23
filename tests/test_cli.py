"""``tuff-bird plot``: a figure or a chart from the command line."""

from __future__ import annotations

import pytest
from helpers import logged_run, spec_in

from tuffbird.cli import main


@pytest.fixture
def logdir(tmp_path):
    for seed in (1, 2):
        logged_run(tmp_path / "logs", f"seed-{seed}", [(step, float(step * seed)) for step in range(4)], group="sac", tag="train/loss")
    return tmp_path / "logs"


def test_plot_writes_a_figure_and_prints_its_caption(logdir, tmp_path, capsys):
    pytest.importorskip("matplotlib")
    output = tmp_path / "loss.svg"
    assert main(["plot", str(logdir), "-t", "train/loss", "-o", str(output)]) == 0
    printed = capsys.readouterr().out
    assert f"[tuffbird] wrote {output}" in printed
    assert "Caption: Lines: mean across runs (n = 2 per curve)." in printed
    assert "<svg" in output.read_text(encoding="utf-8")


@pytest.mark.usefixtures("logdir")
def test_by_default_the_figure_is_named_after_its_tags(tmp_path, monkeypatch):
    pytest.importorskip("matplotlib")
    monkeypatch.chdir(tmp_path)
    assert main(["plot", "logs", "-t", "train/loss"]) == 0
    assert (tmp_path / "train-loss.pdf").read_bytes().startswith(b"%PDF")


@pytest.mark.usefixtures("chart_script")
def test_plot_to_html_writes_the_chart_with_its_options(logdir, tmp_path):
    output = tmp_path / "loss.html"
    assert main(["plot", str(logdir), "-t", "train/loss", "-o", str(output), "--no-group", "--smoothing", "0.3", "--title", "SAC"]) == 0
    spec = spec_in(output.read_text(encoding="utf-8"))
    assert (spec["title"], spec["smoothing"]) == ("SAC", 0.3)
    assert [curve["key"] for curve in spec["panels"][0]["curves"]] == ["sac/seed-1", "sac/seed-2"]


@pytest.mark.usefixtures("chart_script")
def test_plot_to_html_names_the_options_only_figures_take(logdir, tmp_path, capsys):
    assert main(["plot", str(logdir), "-t", "train/loss", "-o", str(tmp_path / "loss.html"), "--band", "std", "--raw"]) == 0
    assert "[tuffbird] --band, --raw: figures only;" in capsys.readouterr().out


def test_plot_says_what_went_wrong_and_exits_with_1(logdir, tmp_path, capsys):
    output = str(tmp_path / "loss.html")
    assert main(["plot", str(tmp_path / "missing"), "-t", "train/loss", "-o", output]) == 1
    assert "no log directory" in capsys.readouterr().out
    assert main(["plot", str(logdir), "-t", "accuracy", "-o", output]) == 1
    assert "logged accuracy" in capsys.readouterr().out
