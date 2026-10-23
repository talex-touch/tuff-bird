"""Reading a log directory back: its runs, their scalars, and curves grouped the way the board groups them.

    import tuffbird
    exp = tuffbird.load("logs")
    fig = exp.plot("eval/return")                 # a figure for a paper (tuff-bird[plot])
    exp.chart("eval/return").save("return.html")  # the board's chart as one offline file
    exp.show("eval/return")                       # in a notebook, live while runs write (tuff-bird[notebook])
"""

from __future__ import annotations

import math
import os
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .board.store import RunState, Store

if TYPE_CHECKING:
    from matplotlib.figure import Figure

    from .charts.chart import Chart
    from .charts.live import Live

    GroupBy = Callable[["RunInfo"], "str | None"] | str | Sequence[str] | None

# The board's colors: TuffEx's six categorical colors, then six more. Pages resolve the variables, so
# a color follows the light or dark theme; figures use the fallback after the comma.
PALETTE = (
    "var(--tx-chart-categorical-1, #4290f0)",
    "var(--tx-chart-categorical-2, #f5b647)",
    "var(--tx-chart-categorical-3, #e8649d)",
    "var(--tx-chart-categorical-4, #8d58ee)",
    "var(--tx-chart-categorical-5, #50c3b6)",
    "var(--tx-chart-categorical-6, #d37536)",
    "#2f9e44",
    "#3b5bdb",
    "#c2255c",
    "#0c8599",
    "#82a31c",
    "#868e96",
)


class _ByDirectory:
    def __repr__(self) -> str:
        return "BY_DIRECTORY"


#: Group runs as the board does: the runs in one directory are seeds of one configuration, and a run
#: at the top of the log directory stays on its own.
BY_DIRECTORY: Any = _ByDirectory()


@dataclass(frozen=True)
class RunInfo:
    """One run: a directory of event files, named by its path under the log directory."""

    id: str
    name: str
    parent: str
    group: str
    #: ``running``, ``idle``, ``finished``, ``failed`` or ``stopped``, as of the last read.
    status: str
    hparams: dict[str, Any]
    start_time: float | None


@dataclass
class Curve:
    """One line on a chart: a run, or a group of runs drawn as their mean with a band."""

    key: str
    label: str
    color: str
    #: Run id → ``(step, value)`` pairs, in the order the runs sort by name.
    runs: dict[str, list[tuple[float, float]]] = field(default_factory=dict)

    @property
    def seeds(self) -> list[list[tuple[float, float]]]:
        return list(self.runs.values())


@dataclass
class _Slot:
    key: str
    label: str
    color: str
    runs: list[str]


class Experiment:
    """Every run under a log directory, written by tuff-bird or by any TensorBoard writer."""

    def __init__(self, logdir: str | os.PathLike[str]) -> None:
        self.logdir = os.path.abspath(os.fspath(logdir))
        self._store = Store(self.logdir)
        self._store.scan()

    def refresh(self) -> Experiment:
        """Reads what the runs have written since the last read."""
        self._store.scan()
        return self

    def __repr__(self) -> str:
        running = sum(state.status == "running" for state in self._store.runs.values())
        return f"<Experiment {self.logdir}: {len(self._store.runs)} runs, {len(self.tags)} tags, {running} running>"

    # ------------------------------------------------------------------ runs and scalars

    @property
    def runs(self) -> list[RunInfo]:
        """The runs, oldest first, in the order the board lists them."""
        return [_info(state) for state in self._ordered()]

    @property
    def tags(self) -> list[str]:
        tags = {tag for state in self._store.runs.values() for tag in state.scalars}
        return sorted(tags, key=_natural_key)

    @property
    def running(self) -> bool:
        """Whether a run was still writing at the last read."""
        return any(state.status == "running" for state in self._store.runs.values())

    def scalars(self, tag: str) -> dict[str, list[tuple[float, float]]]:
        """Run id → ``(step, value)`` pairs, for the runs that logged ``tag``."""
        return {state.id: _pairs(state.scalars[tag]) for state in self._ordered() if state.scalars.get(tag)}

    def curves(self, tag: str, group_by: GroupBy = BY_DIRECTORY) -> list[Curve]:
        """The lines a chart of ``tag`` draws.

        ``group_by`` decides which runs share a line:

        - ``BY_DIRECTORY`` (the default): the runs in one directory, as the board merges them.
        - a config key such as ``"lr"``, or several keys: runs with the same values. Runs without
          the key stay on their own.
        - a function of a :class:`RunInfo` that returns a label, or ``None`` to leave the run alone.
        - ``None``: every run on its own.
        """
        return [
            Curve(slot.key, slot.label, slot.color, {run_id: _pairs(self._store.runs[run_id].scalars[tag]) for run_id in slot.runs})
            for slot in self._slots(tag, group_by)
        ]

    # ------------------------------------------------------------------ outputs

    def plot(self, tags: str | Sequence[str], **options: Any) -> Figure:
        """A figure for a paper; see :func:`tuffbird.figures.plot` for the options. Needs ``tuff-bird[plot]``."""
        from .figures import plot

        return plot(self, tags, **options)

    def chart(self, tags: str | Sequence[str], **options: Any) -> Chart:
        """The board's interactive chart, for a notebook or a file; see :func:`tuffbird.charts.chart_spec`."""
        from .charts import Chart, chart_spec

        self.check_tags(tags)
        return Chart(chart_spec(self, tags, **options))

    def show(self, tags: str | Sequence[str], **options: Any) -> Live:
        """Shows the chart in a notebook, following the runs while they write. Needs ``tuff-bird[notebook]``."""
        from .charts.live import show

        return show(self, tags, **options)

    def check_tags(self, tags: str | Sequence[str]) -> list[str]:
        """``tags`` as a list; raises ``ValueError`` naming the tags no run has logged."""
        wanted = as_tags(tags)
        known = set(self.tags)
        missing = [tag for tag in wanted if tag not in known]
        if missing:
            listed = ", ".join(self.tags[:20]) + (", …" if len(known) > 20 else "")
            raise ValueError(f"no run in {self.logdir} logged {', '.join(missing)}; its tags: {listed or 'none'}")
        return wanted

    # ------------------------------------------------------------------ grouping

    def _ordered(self) -> list[RunState]:
        return sorted(self._store.runs.values(), key=_start_key)

    def _points(self, run_id: str, tag: str, start: int = 0) -> list[tuple[float, float]]:
        state = self._store.runs.get(run_id)
        return _pairs(state.scalars.get(tag, [])[start:]) if state else []

    def _slots(self, tag: str, group_by: GroupBy) -> list[_Slot]:
        ordered = self._ordered()
        prefix = _common_prefix([state.id for state in ordered])
        logged = [state for state in ordered if state.scalars.get(tag)]
        if group_by is BY_DIRECTORY:
            colors = _board_colors(ordered)
            slots: dict[str, _Slot] = {}
            for state in logged:
                parent = state.id.rpartition("/")[0]
                key = f"group:{parent}" if parent else state.id
                if key not in slots:
                    label = _group_label(parent, prefix) if parent else _run_label(state, prefix)
                    slots[key] = _Slot(key, label, colors[key], [])
                slots[key].runs.append(state.id)
            for slot in slots.values():
                slot.runs.sort(key=_natural_key)
            return list(slots.values())
        if group_by is None:
            colors = _board_colors(ordered)
            return [_Slot(state.id, _run_label(state, prefix), colors[state.id], [state.id]) for state in logged]

        label_of = _labeler(group_by)
        groups: dict[str, tuple[Any, list[str]]] = {}
        alone: list[RunState] = []
        for state in logged:
            label = label_of(_info(state))
            if label is None:
                alone.append(state)
            else:
                groups.setdefault(label[0], (label[1], []))[1].append(state.id)
        ordered_groups = sorted(groups.items(), key=lambda item: item[1][0])
        result = [_Slot(f"by:{label}", label, PALETTE[index % len(PALETTE)], sorted(run_ids, key=_natural_key))
                  for index, (label, (_, run_ids)) in enumerate(ordered_groups)]
        for state in alone:
            result.append(_Slot(state.id, _run_label(state, prefix), PALETTE[len(result) % len(PALETTE)], [state.id]))
        return result


def load(logdir: str | os.PathLike[str] = "logs") -> Experiment:
    """Reads every run under ``logdir``, written by tuff-bird or by any TensorBoard writer."""
    if not os.path.isdir(logdir):
        raise FileNotFoundError(f"no log directory at {os.path.abspath(logdir)}")
    return Experiment(logdir)


def as_tags(tags: str | Sequence[str]) -> list[str]:
    wanted = [tags] if isinstance(tags, str) else list(tags)
    if not wanted:
        raise ValueError("name at least one tag")
    return wanted


def hex_color(color: str) -> str:
    """A palette color without its CSS variable: ``var(--x, #4290f0)`` → ``#4290f0``."""
    match = re.fullmatch(r"var\(\s*--[\w-]+\s*,\s*(.+?)\s*\)", color)
    return match.group(1) if match else color


# ---------------------------------------------------------------------- helpers


def _pairs(points: list[list[float]]) -> list[tuple[float, float]]:
    return [(point[0], point[1]) for point in points]


def _info(state: RunState) -> RunInfo:
    meta = state.meta()
    return RunInfo(
        id=state.id, name=meta["name"], parent=meta["parent"], group=meta["group"], status=state.status,
        hparams=dict(state.hparams), start_time=meta["startTime"],
    )


def _natural_key(text: str) -> tuple[Any, ...]:
    """Orders ``seed-2`` before ``seed-10``, as the board does."""
    return tuple(int(part) if index % 2 else part.casefold() for index, part in enumerate(re.split(r"(\d+)", text)))


def _start_key(state: RunState) -> tuple[Any, ...]:
    # Runs started in the same second keep their name order, which puts the seeds of one launch together.
    start = state.start_time or state.first_wall
    return (math.floor(start) if start is not None else math.inf, _natural_key(state.id))


def _common_prefix(ids: list[str]) -> list[str]:
    if len(ids) < 2:
        return []
    split = [run_id.split("/") for run_id in ids]
    prefix: list[str] = []
    for index, part in enumerate(split[0]):
        # Never strip a run's own name, only the directories every run shares.
        if any(len(parts) <= index + 1 or parts[index] != part for parts in split):
            break
        prefix.append(part)
    return prefix


def _run_label(state: RunState, prefix: list[str]) -> str:
    return state.meta()["name"] if state.id == "." else "/".join(state.id.split("/")[len(prefix):])


def _group_label(parent: str, prefix: list[str]) -> str:
    # When every run sits in this one directory, the shared prefix is the whole key.
    parts = parent.split("/")
    return "/".join(parts[len(prefix):]) or parts[-1] or parent


def _board_colors(ordered: list[RunState]) -> dict[str, str]:
    """The colors a freshly opened board gives each run and each merged group."""
    colors: dict[str, str] = {}
    groups = 0
    for index, state in enumerate(ordered):
        colors[state.id] = PALETTE[index % len(PALETTE)]
        parent = state.id.rpartition("/")[0]
        if parent and f"group:{parent}" not in colors:
            colors[f"group:{parent}"] = PALETTE[groups % len(PALETTE)]
            groups += 1
    return colors


def _labeler(group_by: Any) -> Callable[[RunInfo], tuple[str, Any] | None]:
    """A function giving a run's group label and the key its group sorts by, or ``None`` to leave it alone."""
    if callable(group_by):
        def by_function(run: RunInfo) -> tuple[str, Any] | None:
            label = group_by(run)
            return None if label is None else (str(label), _natural_key(str(label)))

        return by_function
    try:
        keys = [group_by] if isinstance(group_by, str) else list(group_by)
    except TypeError:
        keys = []
    if not keys or not all(isinstance(key, str) for key in keys):
        raise TypeError("group_by takes BY_DIRECTORY, None, a config key, a list of config keys, or a function of a run")

    def by_hparams(run: RunInfo) -> tuple[str, Any] | None:
        if any(key not in run.hparams for key in keys):
            return None
        values = [run.hparams[key] for key in keys]
        return ", ".join(f"{key}={_format_hparam(value)}" for key, value in zip(keys, values, strict=True)), tuple(_value_key(value) for value in values)

    return by_hparams


def _format_hparam(value: Any) -> str:
    return f"{value:g}" if isinstance(value, float) else str(value)


def _value_key(value: Any) -> tuple[Any, ...]:
    # Numbers sort by value (0.0003 before 0.001), everything else by name.
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return (0, value)
    return (1, _natural_key(str(value)))
