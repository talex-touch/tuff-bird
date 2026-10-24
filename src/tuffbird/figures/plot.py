"""Figures for papers: each curve as the estimate across its runs with a band, in the board's colors."""

from __future__ import annotations

import io
import math
import warnings
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

import matplotlib as mpl
import numpy as np
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter

from ..experiment import BY_DIRECTORY, hex_color
from .stats import summarize

if TYPE_CHECKING:
    from matplotlib.axes import Axes

    from ..experiment import Experiment, GroupBy

# Small type, a light grid and no top or right spine, sized for a 3.4-inch column.
STYLE: dict[str, Any] = {
    "font.size": 8,
    "axes.titlesize": 9,
    "axes.labelsize": 8,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "legend.fontsize": 7,
    "axes.edgecolor": "#c0c4cc",
    "axes.labelcolor": "#606266",
    "xtick.color": "#909399",
    "ytick.color": "#909399",
    "axes.grid": True,
    "grid.color": "#ebeef5",
    "grid.linewidth": 0.8,
    "axes.spines.top": False,
    "axes.spines.right": False,
}
# Read when a file is written rather than when the figure is drawn, so PaperFigure.savefig sets them.
# Type 42 embeds TrueType fonts, which venues accept and editors can change; SVG text stays text.
SAVE_STYLE: dict[str, Any] = {"pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none", "savefig.dpi": 300}

_BAND_TEXT = {
    "std": "±1 standard deviation across runs",
    "se": "±1 standard error across runs",
    "minmax": "the lowest to the highest run",
}
_ESTIMATOR_TEXT = {"mean": "mean", "iqm": "interquartile mean (IQM)", "median": "median"}
_ESTIMATOR_SHORT = {"mean": "mean", "iqm": "IQM", "median": "median"}


class PaperFigure(Figure):
    """A matplotlib figure that saves with embedded TrueType fonts at 300 dpi; draw on it as on any figure."""

    def savefig(self, fname: Any, *args: Any, **kwargs: Any) -> None:
        with mpl.rc_context(SAVE_STYLE):
            super().savefig(fname, *args, **kwargs)

    def _repr_png_(self) -> tuple[bytes, dict[str, int]]:
        # Notebooks show it without pyplot, at its size in inches on a 100-dpi screen, sharp on HiDPI ones.
        buffer = io.BytesIO()
        super().savefig(buffer, format="png", dpi=200)
        return buffer.getvalue(), {"width": round(self.get_figwidth() * 100)}


def plot(
    experiment: Experiment,
    tags: str | Sequence[str],
    *,
    group_by: GroupBy = BY_DIRECTORY,
    smoothing: float = 0.6,
    estimator: str = "mean",
    band: str | None = "ci",
    truncate: bool = True,
    raw: bool = False,
    confidence: float = 0.95,
    resamples: int = 2000,
    max_points: int | None = 2000,
    ax: Axes | Sequence[Axes] | None = None,
    size: tuple[float, float] | None = None,
    title: str | None = None,
) -> Figure:
    """One panel per tag; each curve is the ``estimator`` across its runs with a ``band`` around it.

    By default, the mean with a 95% bootstrap confidence interval, the interval estimate Agarwal et
    al. (2021) recommend, over the steps every run reached; their interquartile mean is ``"iqm"``.
    ``fig.tuffbird_caption`` says what the lines and the band show, with the number of runs, ready
    for the figure's caption. Pass ``ax`` to draw on axes of your own (one per tag).
    """
    tags = experiment.check_tags(tags)
    if ax is None:
        with mpl.rc_context(STYLE):
            fig: Figure = PaperFigure(figsize=size or (min(7.0, 3.4 * len(tags)), 2.3), layout="constrained")
            axes = list(fig.subplots(1, len(tags), squeeze=False)[0])
        style: dict[str, Any] = STYLE
    else:
        axes = [ax] if not isinstance(ax, (Sequence, np.ndarray)) else list(np.ravel(ax))
        if len(axes) != len(tags):
            raise ValueError(f"got {len(axes)} axes for {len(tags)} tags")
        fig = axes[0].figure
        style = {}

    legend: dict[str, tuple[Any, str]] = {}
    counts: set[int] = set()
    any_truncated = False
    with mpl.rc_context(style):
        for axis, tag in zip(axes, tags, strict=True):
            for curve in experiment.curves(tag, group_by):
                summary = summarize(
                    curve.seeds, smoothing=smoothing, estimator=estimator, band=band, truncate=truncate,
                    confidence=confidence, resamples=resamples, max_points=max_points,
                )
                if summary.disjoint:
                    warnings.warn(f"{tag}: the runs of {curve.label} share no steps, so its curve keeps every step", stacklevel=2)
                any_truncated = any_truncated or summary.truncated
                color = hex_color(curve.color)
                if raw and smoothing > 0:
                    axis.plot(summary.steps, summary.raw, color=color, alpha=0.22, linewidth=0.7)
                if summary.low is not None:
                    axis.fill_between(summary.steps, summary.low, summary.high, color=color, alpha=0.16, linewidth=0)
                (line,) = axis.plot(summary.steps, summary.center, color=color, linewidth=1.5)
                counts.add(summary.runs)
                label = f"{curve.label} (n={summary.runs})" if summary.runs > 1 else curve.label
                legend.setdefault(curve.key, (line, label))
            axis.set_xlabel("step")
            axis.set_ylabel(tag)
            axis.xaxis.set_major_formatter(FuncFormatter(si_format))
        if title:
            if len(axes) == 1:
                axes[0].set_title(title, loc="left", fontweight="bold")
            else:
                fig.suptitle(title, x=0.01, ha="left", fontweight="bold")
        if len(legend) > 1:
            handles, labels = zip(*legend.values(), strict=True)
            axes[0].legend(handles, labels, frameon=False, loc="best")
    fig.tuffbird_caption = caption(  # type: ignore[attr-defined]
        estimator=estimator, band=band or "none", confidence=confidence, resamples=resamples,
        smoothing=smoothing, truncated=any_truncated, counts=counts, raw=raw,
    )
    return fig


def caption(*, estimator: str, band: str, confidence: float, resamples: int, smoothing: float, truncated: bool, counts: set[int], raw: bool) -> str:
    """What a figure's lines and band show, as one paragraph for its caption."""
    smoothed = f"a debiased exponential moving average (weight {smoothing:g})" if smoothing > 0 else ""
    if counts <= {1}:
        text = "Lines: single runs" + (f", smoothed with {smoothed}." if smoothed else ".")
        return text + (" Faint lines: the values as logged." if raw and smoothed else "")
    low, high = min(counts), max(counts)
    n = f"n = {high}" if low == high else f"n = {low}–{high}"
    sentences = [f"Lines: {_ESTIMATOR_TEXT[estimator]} across runs ({n} per curve)."]
    if band == "ci":
        sentences.append(f"Shaded: {confidence:.0%} bootstrap confidence interval of the {_ESTIMATOR_SHORT[estimator]} ({resamples:,} resamples).")
    elif band in _BAND_TEXT:
        sentences.append(f"Shaded: {_BAND_TEXT[band]}.")
    if smoothed:
        sentences.append(f"Each run is smoothed with {smoothed} before aggregating.")
    if raw and smoothed:
        sentences.append(f"Faint lines: the {_ESTIMATOR_SHORT[estimator]} of the values as logged.")
    if truncated:
        sentences.append("Steps stop where the shortest run stops.")
    return " ".join(sentences)


def si_format(value: float, _position: Any = None) -> str:
    """Step ticks as the board writes them: 2500, 50k, 1.5M."""
    magnitude = abs(value)
    if magnitude >= 1e4:
        for size, unit in ((1e9, "G"), (1e6, "M"), (1e3, "k")):
            if magnitude >= size:
                return f"{value / size:.3g}{unit}"
    return f"{value:g}"


def chart_png(spec: dict[str, Any], *, width: float = 6.4, dpi: int = 150) -> bytes:
    """A picture of an interactive chart (see :func:`tuffbird.charts.chart_spec`) as the board draws it.

    Each group is the mean of its smoothed runs at the union of their steps with a one-standard-
    deviation band, so the picture matches the chart it stands in for.
    """
    panels = spec["panels"]
    columns = 1 if len(panels) == 1 else 2
    rows = math.ceil(len(panels) / columns)
    with mpl.rc_context(STYLE):
        fig = Figure(figsize=(width, 0.3 + 2.4 * rows), layout="constrained")
        axes = fig.subplots(rows, columns, squeeze=False).ravel()
        legend: dict[str, tuple[Any, str]] = {}
        for axis, panel in zip(axes, panels, strict=False):
            for curve in panel["curves"]:
                runs = [[(float(step), float(value)) for step, value in run["points"]] for run in curve["runs"]]
                summary = summarize(runs, smoothing=spec["smoothing"], band="std", truncate=False, max_points=None)
                color = hex_color(curve["color"])
                if spec.get("showRaw", True) and spec["smoothing"] > 0:
                    axis.plot(summary.steps, summary.raw, color=color, alpha=0.22, linewidth=0.7)
                if summary.low is not None:
                    axis.fill_between(summary.steps, summary.low, summary.high, color=color, alpha=0.16, linewidth=0)
                (line,) = axis.plot(summary.steps, summary.center, color=color, linewidth=1.5)
                legend.setdefault(curve["key"], (line, curve["name"]))
            axis.set_title(panel["tag"], loc="left", fontweight="bold")
            axis.xaxis.set_major_formatter(FuncFormatter(si_format))
            if spec.get("logX"):
                axis.set_xscale("log")
        for axis in axes[len(panels):]:
            axis.set_visible(False)
        if legend:
            handles, labels = zip(*legend.values(), strict=True)
            fig.legend(handles, labels, loc="outside upper left", ncols=min(len(labels), 6), frameon=False)
        buffer = io.BytesIO()
        fig.savefig(buffer, format="png", dpi=dpi)
    return buffer.getvalue()
