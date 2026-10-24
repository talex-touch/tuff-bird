"""Figures for papers: the statistics behind each curve, its caption, and the files a figure writes."""

from __future__ import annotations

import warnings

import pytest
from helpers import logged_run

import tuffbird

np = pytest.importorskip("numpy")
pytest.importorskip("matplotlib")
from matplotlib.figure import Figure  # noqa: E402

from tuffbird.charts import chart_spec  # noqa: E402
from tuffbird.figures import PaperFigure, caption, chart_png, smooth_ema, summarize  # noqa: E402
from tuffbird.figures.plot import si_format  # noqa: E402


def png_width(png: bytes) -> int:
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    return int.from_bytes(png[16:20], "big")


@pytest.fixture
def experiment(tmp_path):
    """A run at the top and three seeds of different lengths in one directory, created in name order."""
    logged_run(tmp_path, "baseline", [(step, 2.0) for step in range(5)])
    for seed in range(3):
        logged_run(tmp_path, f"seed-{seed}", [(step, float(step + seed)) for step in range(5 + seed)], group="sac")
    return tuffbird.load(tmp_path)


# ---------------------------------------------------------------------- statistics


def test_smoothing_is_the_boards_debiased_average():
    assert smooth_ema([1, 2, 3], 0.5) == pytest.approx([1, 5 / 3, 17 / 7])


def test_smoothing_leaves_flat_series_and_zero_weight_alone_and_steps_over_nan():
    assert smooth_ema([2, 2, 2], 0.9).tolist() == [2, 2, 2]
    assert smooth_ema([1, 5, 2], 0).tolist() == [1, 5, 2]
    smoothed = smooth_ema([1, float("nan"), 3], 0.5)
    assert np.isnan(smoothed[1])
    assert smoothed[[0, 2]] == pytest.approx([1, 7 / 3])


def test_by_default_the_steps_stop_where_the_shortest_run_stops():
    long = [(step, 1.0) for step in range(10)]
    short = [(step, 3.0) for step in range(5)]
    summary = summarize([long, short], smoothing=0)
    assert summary.truncated
    assert summary.steps.tolist() == [0, 1, 2, 3, 4]
    assert summary.center.tolist() == [2.0] * 5

    kept = summarize([long, short], smoothing=0, truncate=False)
    assert not kept.truncated
    assert kept.steps.tolist() == list(range(10))
    # Past the shortest run, the estimate is of the one run left.
    assert kept.center.tolist() == [2.0] * 5 + [1.0] * 5
    assert kept.count.tolist() == [2] * 5 + [1] * 5
    # Runs that stop together lose no steps.
    assert not summarize([long, long], smoothing=0).truncated


def test_one_run_has_no_band():
    summary = summarize([[(0, 1.0), (1, 2.0)]], smoothing=0)
    assert (summary.runs, summary.low, summary.high, summary.truncated) == (1, None, None, False)


@pytest.mark.parametrize(("estimator", "expected"), [("mean", 133.25), ("median", 6.5), ("iqm", 8.75)])
def test_each_estimator_across_runs(estimator, expected):
    # The interquartile mean drops two of the eight runs at each end: the mean of 2, 3, 10 and 20.
    runs = [[(0, value)] for value in (0.0, 1.0, 2.0, 3.0, 10.0, 20.0, 30.0, 1000.0)]
    assert summarize(runs, smoothing=0, estimator=estimator).center.tolist() == [expected]


@pytest.mark.parametrize(("band", "spread"), [("std", (14 / 3) ** 0.5), ("se", (7 / 3) ** 0.5)])
def test_deviation_bands_sit_around_the_estimate(band, spread):
    summary = summarize([[(0, value)] for value in (1.0, 2.0, 6.0)], smoothing=0, band=band)
    assert summary.low.tolist() == pytest.approx([3 - spread])
    assert summary.high.tolist() == pytest.approx([3 + spread])


def test_minmax_spans_the_runs_and_none_draws_no_band():
    runs = [[(0, value)] for value in (1.0, 2.0, 6.0)]
    minmax = summarize(runs, smoothing=0, band="minmax")
    assert (minmax.low.tolist(), minmax.high.tolist()) == ([1.0], [6.0])
    assert summarize(runs, smoothing=0, band="none").low is None


def test_the_bootstrap_interval_is_repeatable_and_holds_the_estimate():
    runs = [[(step, value + step) for step in range(4)] for value in (1.0, 2.0, 4.0, 7.0)]
    first = summarize(runs, smoothing=0, resamples=500)
    again = summarize(runs, smoothing=0, resamples=500)
    assert (first.low.tolist(), first.high.tolist()) == (again.low.tolist(), again.high.tolist())
    assert np.all(first.low < first.center)
    assert np.all(first.center < first.high)

    same = summarize([[(0, 1.0), (1, 2.0)]] * 3, smoothing=0)
    assert same.low.tolist() == same.center.tolist() == same.high.tolist() == [1.0, 2.0]


def test_steps_are_put_in_order_and_a_repeated_step_keeps_its_last_value():
    summary = summarize([[(2, 3.0), (0, 1.0), (1, 5.0), (1, 2.0)]], smoothing=0)
    assert summary.steps.tolist() == [0, 1, 2]
    assert summary.center.tolist() == [1.0, 2.0, 3.0]


def test_max_points_thins_evenly_and_keeps_both_ends():
    summary = summarize([[(step, float(step)) for step in range(1000)]], smoothing=0, max_points=100)
    assert summary.steps.size == 100
    assert (summary.steps[0], summary.steps[-1]) == (0, 999)
    # Thinning reads the curve at fewer steps; it does not move it.
    assert summary.center.tolist() == summary.steps.tolist()


def test_runs_without_points_make_an_empty_curve():
    summary = summarize([[], []])
    assert (summary.runs, summary.steps.size) == (0, 0)


@pytest.mark.parametrize("options", [{"estimator": "max"}, {"band": "iqr"}])
def test_summarize_names_the_choices_it_takes(options):
    with pytest.raises(ValueError, match="must be one of"):
        summarize([[(0, 1.0)]], **options)


# ---------------------------------------------------------------------- figures


def test_plot_draws_a_panel_per_tag_and_writes_its_caption(experiment):
    figure = experiment.plot("loss")
    assert isinstance(figure, PaperFigure)
    axis = figure.axes[0]
    assert axis.get_ylabel() == "loss"
    assert [text.get_text() for text in axis.get_legend().get_texts()] == ["baseline", "sac (n=3)"]
    assert figure.tuffbird_caption == (
        "Lines: mean across runs (n = 1–3 per curve). "
        "Shaded: 95% bootstrap confidence interval of the mean (2,000 resamples). "
        "Each run is smoothed with a debiased exponential moving average (weight 0.6) before aggregating. "
        "Steps stop where the shortest run stops."
    )


def test_saved_figures_embed_their_fonts_and_keep_text_as_text(experiment, tmp_path):
    figure = experiment.plot("loss", band="std")
    for suffix in ("pdf", "svg", "png"):
        figure.savefig(tmp_path / f"loss.{suffix}")
    assert b"/FontFile2" in (tmp_path / "loss.pdf").read_bytes()
    assert "<text" in (tmp_path / "loss.svg").read_text(encoding="utf-8")
    # 3.4 inches at 300 dpi.
    assert png_width((tmp_path / "loss.png").read_bytes()) == 1020


def test_plot_draws_on_axes_of_your_own(experiment):
    figure = Figure()
    axes = figure.subplots(1, 2)
    assert experiment.plot("loss", ax=axes[0]) is figure
    with pytest.raises(ValueError, match="got 2 axes for 1 tags"):
        experiment.plot("loss", ax=axes)


def test_a_curve_whose_runs_share_no_steps_keeps_them_all_and_says_so(tmp_path):
    logged_run(tmp_path, "seed-1", [(0, 1.0), (1, 1.0)], group="sac")
    logged_run(tmp_path, "seed-2", [(5, 1.0), (6, 1.0)], group="sac")
    with pytest.warns(UserWarning, match="share no steps"):
        figure = tuffbird.load(tmp_path).plot("loss")
    assert "shortest run" not in figure.tuffbird_caption


def test_a_caption_says_nothing_of_the_shortest_run_when_the_runs_stop_together(tmp_path):
    for seed in (1, 2):
        logged_run(tmp_path, f"seed-{seed}", [(step, float(step * seed)) for step in range(4)], group="sac")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        figure = tuffbird.load(tmp_path).plot("loss")
    assert not [warning for warning in caught if "share no steps" in str(warning.message)]
    assert figure.tuffbird_caption.startswith("Lines: mean across runs (n = 2 per curve).")
    assert "shortest run" not in figure.tuffbird_caption


def test_the_caption_follows_the_options():
    assert caption(estimator="mean", band="ci", confidence=0.95, resamples=2000, smoothing=0, truncated=False, counts={1}, raw=False) == "Lines: single runs."
    assert caption(estimator="mean", band="ci", confidence=0.95, resamples=2000, smoothing=0.6, truncated=False, counts={1}, raw=True) == (
        "Lines: single runs, smoothed with a debiased exponential moving average (weight 0.6). Faint lines: the values as logged."
    )
    assert caption(estimator="iqm", band="se", confidence=0.9, resamples=500, smoothing=0.9, truncated=False, counts={4}, raw=True) == (
        "Lines: interquartile mean (IQM) across runs (n = 4 per curve). Shaded: ±1 standard error across runs. "
        "Each run is smoothed with a debiased exponential moving average (weight 0.9) before aggregating. "
        "Faint lines: the IQM of the values as logged."
    )


def test_step_ticks_read_as_on_the_board():
    assert [si_format(value) for value in (0, 2500, 50_000, 1_500_000, 2e9)] == ["0", "2500", "50k", "1.5M", "2G"]


def test_chart_png_draws_a_chart_spec(experiment):
    assert png_width(chart_png(chart_spec(experiment, "loss"), width=4, dpi=50)) == 200
