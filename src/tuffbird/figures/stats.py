"""How a figure turns the runs of one curve into a line and a band.

Each run is smoothed on its own steps, then every run is read at shared steps and the estimate is
taken across runs at each step. By default the steps stop where the shortest run stops, so the end
of a curve is never an average over fewer runs than its start.
"""

from __future__ import annotations

import math
import warnings
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

ESTIMATORS = ("mean", "iqm", "median")
BANDS = ("ci", "std", "se", "minmax", "none")
# Bootstrap draws are evaluated in batches of about this many bytes.
_BATCH_BYTES = 32 * 2**20


@dataclass
class Summary:
    """One curve, ready to draw."""

    steps: np.ndarray
    #: The estimate across runs at each step, of the smoothed values.
    center: np.ndarray
    low: np.ndarray | None
    high: np.ndarray | None
    #: The same estimate of the unsmoothed values.
    raw: np.ndarray
    #: How many runs have a value at each step.
    count: np.ndarray
    runs: int
    #: Whether steps were dropped to keep to the range every run reached.
    truncated: bool
    #: Whether the runs share no range of steps, so the curve keeps every step.
    disjoint: bool = False


def smooth_ema(values: Sequence[float] | np.ndarray, weight: float) -> np.ndarray:
    """TensorBoard's debiased exponential moving average, computed as the board's chart computes it."""
    values = np.asarray(values, dtype=float)
    w = min(0.999, max(0.0, float(weight))) if math.isfinite(weight) else 0.0
    if w == 0 or values.size == 0 or bool(np.all(values == values[0])):
        return values.copy()
    smoothed = np.empty_like(values)
    last = 0.0
    count = 0
    for index, value in enumerate(values.tolist()):
        if not math.isfinite(value):
            smoothed[index] = value
            continue
        last = last * w + (1 - w) * value
        count += 1
        smoothed[index] = last / (1 - w**count)
    return smoothed


def summarize(
    runs: Sequence[Sequence[tuple[float, float]]],
    *,
    smoothing: float = 0.6,
    estimator: str = "mean",
    band: str | None = "ci",
    truncate: bool = True,
    confidence: float = 0.95,
    resamples: int = 2000,
    max_points: int | None = 2000,
    seed: int = 0,
) -> Summary:
    """The estimate across ``runs`` (each a list of ``(step, value)``) and the band around it.

    ``band`` is ``"ci"`` (a percentile bootstrap confidence interval of the estimate, over runs),
    ``"std"`` or ``"se"`` (one standard deviation or standard error around it), ``"minmax"``, or
    ``"none"``. A single run has no band. ``max_points`` thins the shared steps evenly after
    smoothing, which keeps vector files small without changing the shape of the curve.
    """
    if estimator not in ESTIMATORS:
        raise ValueError(f"estimator must be one of {', '.join(ESTIMATORS)}")
    band = band or "none"
    if band not in BANDS:
        raise ValueError(f"band must be one of {', '.join(BANDS)}")
    series = [pair for pair in (_ordered(points) for points in runs) if pair[0].size]
    if not series:
        empty = np.empty(0)
        return Summary(empty, empty, None, None, empty, np.empty(0, dtype=int), 0, False)

    smoothed = [smooth_ema(values, smoothing) for _, values in series]
    steps = np.unique(np.concatenate([run_steps for run_steps, _ in series]))
    truncated = disjoint = False
    if truncate and len(series) > 1:
        first = max(run_steps[0] for run_steps, _ in series)
        last = min(run_steps[-1] for run_steps, _ in series)
        shared = steps[(steps >= first) & (steps <= last)]
        if not shared.size:
            disjoint = True
        elif shared.size < steps.size:
            steps = shared
            truncated = True
    if max_points and steps.size > max_points:
        steps = steps[np.unique(np.linspace(0, steps.size - 1, max_points).round().astype(int))]

    raw = np.vstack([_read(steps, run_steps, values) for run_steps, values in series])
    smooth = np.vstack([_read(steps, run_steps, values) for (run_steps, _), values in zip(series, smoothed, strict=True)])
    center = _estimate(smooth, estimator)
    count = np.sum(~np.isnan(smooth), axis=0)
    low = high = None
    if len(series) > 1 and band != "none":
        with warnings.catch_warnings(), np.errstate(invalid="ignore", divide="ignore"):
            warnings.simplefilter("ignore", RuntimeWarning)
            if band == "ci":
                low, high = _bootstrap(smooth, estimator, confidence, resamples, np.random.default_rng(seed))
            elif band == "std":
                spread = np.nanstd(smooth, axis=0)
                low, high = center - spread, center + spread
            elif band == "se":
                spread = np.nanstd(smooth, axis=0, ddof=1) / np.sqrt(count)
                low, high = center - spread, center + spread
            else:
                low, high = np.nanmin(smooth, axis=0), np.nanmax(smooth, axis=0)
    return Summary(steps, center, low, high, _estimate(raw, estimator), count, len(series), truncated, disjoint)


def _ordered(points: Sequence[tuple[float, float]]) -> tuple[np.ndarray, np.ndarray]:
    """Steps in order with their values; a step logged twice keeps its last value, as the board reads it."""
    array = np.asarray(points, dtype=float).reshape(-1, 2)
    array = array[np.isfinite(array[:, 0])]
    if array.shape[0] > 1 and np.any(np.diff(array[:, 0]) < 0):
        array = array[np.argsort(array[:, 0], kind="stable")]
    if array.shape[0] > 1:
        last = np.append(array[1:, 0] != array[:-1, 0], True)
        array = array[last]
    return array[:, 0], array[:, 1]


def _read(steps: np.ndarray, run_steps: np.ndarray, values: np.ndarray) -> np.ndarray:
    """A run's values at ``steps``, interpolated between its own steps and missing outside them."""
    return np.interp(steps, run_steps, values, left=np.nan, right=np.nan)


def _estimate(matrix: np.ndarray, estimator: str) -> np.ndarray:
    """The estimate over the run axis (second to last), skipping runs with no value at a step."""
    with warnings.catch_warnings(), np.errstate(invalid="ignore", divide="ignore"):
        warnings.simplefilter("ignore", RuntimeWarning)
        if estimator == "mean":
            return np.nanmean(matrix, axis=-2)
        if estimator == "median":
            return np.nanmedian(matrix, axis=-2)
        # Interquartile mean: drop a quarter of the runs at each end, as scipy's trim_mean(0.25) does.
        ordered = np.sort(matrix, axis=-2)
        count = np.sum(~np.isnan(ordered), axis=-2, keepdims=True)
        cut = (count * 0.25).astype(int)
        zeros = np.zeros_like(ordered[..., :1, :])
        totals = np.concatenate([zeros, np.nancumsum(ordered, axis=-2)], axis=-2)
        kept = np.take_along_axis(totals, count - cut, axis=-2) - np.take_along_axis(totals, cut, axis=-2)
        return (kept / (count - 2 * cut)).squeeze(-2)


def _bootstrap(smooth: np.ndarray, estimator: str, confidence: float, resamples: int, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    runs, steps = smooth.shape
    batch = max(1, _BATCH_BYTES // (8 * runs * max(1, steps)))
    estimates = np.empty((resamples, steps))
    for start in range(0, resamples, batch):
        stop = min(resamples, start + batch)
        picks = rng.integers(0, runs, size=(stop - start, runs))
        estimates[start:stop] = _estimate(smooth[picks], estimator)
    tail = (1 - confidence) / 2
    low, high = np.nanquantile(estimates, [tail, 1 - tail], axis=0)
    return low, high
