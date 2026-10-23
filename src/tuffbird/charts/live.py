"""The chart in a notebook while runs write: a widget that a background thread keeps current, swapped
for a saved :class:`~tuffbird.charts.Chart` once every run has stopped, so the notebook keeps a chart
that still opens, interactive, when no kernel is running.
"""

from __future__ import annotations

import contextvars
import logging
import threading
import time
from collections.abc import Sequence
from typing import Any

try:
    import anywidget
    import traitlets
    from IPython import get_ipython
    from IPython.display import display
except ImportError as error:
    raise ImportError('the live chart needs anywidget: pip install "tuff-bird[notebook]"') from error

from ..experiment import BY_DIRECTORY, Experiment, as_tags
from .chart import Chart, bundle, chart_spec, wire_points

logger = logging.getLogger("tuffbird")

# How long every run must have stopped before the live chart is saved. A sweep that starts its next
# run a few seconds after the last one finished keeps following.
SETTLE_SECS = 30.0


class ChartWidget(anywidget.AnyWidget):
    """The chart as a Jupyter widget. New points arrive as ``append`` messages; a new curve or run, as a new ``spec``.

    In the kernel, ``spec`` holds every point: appends extend it in place without sending it, so a view
    restored after a reload starts from the whole chart. A view that finds it has missed points asks for
    the spec again with a ``sync`` message.
    """

    # A trait rather than a class attribute, so the script is read when a chart is shown, not on import.
    _esm = traitlets.Unicode().tag(sync=True)
    spec = traitlets.Dict().tag(sync=True)
    #: Set once the saved chart has replaced the widget in the output that showed it. A view still
    #: drawing is in a page opened since, where the output stays the widget, and says so.
    saved = traitlets.Bool(False).tag(sync=True)


# Live charts by the cell and the call that showed them; running the cell again replaces its chart.
_shown: dict[tuple[Any, ...], Live] = {}
_shown_lock = threading.Lock()


def show(experiment: Experiment, tags: str | Sequence[str], *, live: bool | None = None, interval: float = 1.0, **options: Any) -> Live:
    """Shows the chart of ``tags`` as the cell's output.

    While a run is writing, the output is a widget that follows the log directory every
    ``interval`` seconds from a background thread, so the cell can go on to train. When every run
    has stopped for ``SETTLE_SECS``, the widget is replaced by a saved :class:`Chart`, with a
    picture inside for viewers that run no scripts. ``live=True`` follows even when nothing is
    running yet; ``live=False`` shows the saved chart now. Other options are :func:`chart_spec`'s.
    """
    shell = get_ipython()
    if shell is None:
        raise RuntimeError("show() draws in a notebook; elsewhere, save the chart: experiment.chart(tags).save('chart.html')")
    tags = as_tags(tags)
    chart = Live(Experiment(experiment.logdir), tags, options, interval)
    key = (_cell_id(shell), chart.logdir, tuple(tags), repr(sorted(options.items())))
    with _shown_lock:
        previous = _shown.pop(key, None)
    if previous is not None:
        previous.cancel()
    if not (chart._experiment.running if live is None else live):
        chart._experiment.check_tags(tags)
        chart.chart = Chart(chart_spec(chart._experiment, tags, **options))
        display(chart.chart)
        return chart
    with _shown_lock:
        _shown[key] = chart
    chart._start()
    return chart


class Live:
    """What :func:`show` returns. ``chart`` is the saved :class:`Chart` once the runs have stopped."""

    def __init__(self, experiment: Experiment, tags: list[str], options: dict[str, Any], interval: float) -> None:
        self.logdir = experiment.logdir
        self.tags = tags
        self.chart: Chart | None = None
        # Only the thread reads this experiment once it starts.
        self._experiment = experiment
        self._options = options
        self._interval = interval
        self._stop = threading.Event()
        self._resync = threading.Event()
        self._save_on_stop = True
        self._thread: threading.Thread | None = None
        self._widget: ChartWidget | None = None
        self._handle: Any = None
        self._layout: Any = None
        # Each run's points in the widget's spec, by tag and run.
        self._series: dict[tuple[str, str], list[Any]] = {}

    def __repr__(self) -> str:
        state = "saved" if self.chart is not None else "following" if self.following else "stopped"
        return f"<Live chart of {', '.join(self.tags)}: {state}>"

    def _ipython_display_(self) -> None:
        """Nothing to add: :func:`show` has already put the chart in the cell's output."""

    @property
    def following(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def stop(self) -> None:
        """Stops following and saves the chart as it is now."""
        self._halt(save=True)

    def cancel(self) -> None:
        """Stops following without saving the chart, and closes the widget; the next :func:`show` of the same cell does this."""
        self._halt(save=False)
        if self._widget is not None:
            self._widget.close()

    # ------------------------------------------------------------------ the thread

    def _start(self) -> None:
        spec = self._full_spec()
        self._widget = ChartWidget(_esm=bundle().source, spec=spec)
        self._widget.on_msg(self._on_message)
        self._handle = display(self._widget, display_id=True)
        # The thread sends in the context of the cell that showed the chart. In its own, ipykernel 7 takes
        # the context of its latest request, which can be one a frontend sent from a subshell it has since
        # deleted: a view's reply to the thread then goes to that subshell, and the kernel drops it.
        context = contextvars.copy_context()
        self._thread = threading.Thread(target=context.run, args=(self._follow,), name="tuffbird-live-chart", daemon=True)
        self._thread.start()

    def _on_message(self, _widget: Any, content: Any, _buffers: Any) -> None:
        # Runs on the kernel's main thread, once the cell it is running has finished; the thread answers.
        if isinstance(content, dict) and content.get("type") == "sync":
            self._resync.set()

    def _halt(self, *, save: bool) -> None:
        thread = self._thread
        if thread is None or not thread.is_alive():
            return
        self._save_on_stop = save
        self._stop.set()
        if thread is not threading.current_thread():
            thread.join(timeout=30)

    def _follow(self) -> None:
        quiet_since: float | None = None
        try:
            while not self._stop.wait(self._interval):
                self._experiment.refresh()
                self._push()
                if self._experiment.running or not self._series:
                    quiet_since = None
                    continue
                quiet_since = quiet_since or time.monotonic()
                if time.monotonic() - quiet_since >= SETTLE_SECS:
                    self._save()
                    return
            if self._save_on_stop:
                self._save()
        except Exception:
            logger.exception("the live chart of %s stopped following %s", ", ".join(self.tags), self.logdir)

    def _full_spec(self) -> dict[str, Any]:
        spec = chart_spec(self._experiment, self.tags, **{**self._options, "max_points": None})
        self._layout = self._current_layout()
        self._series = {(panel["tag"], run["id"]): run["points"] for panel in spec["panels"] for curve in panel["curves"] for run in curve["runs"]}
        return spec

    def _current_layout(self) -> tuple[Any, ...]:
        group_by = self._options.get("group_by", BY_DIRECTORY)
        return tuple(
            (tag, tuple((slot.key, slot.label, slot.color, tuple(slot.runs)) for slot in self._experiment._slots(tag, group_by)))
            for tag in self.tags
        )

    def _push(self) -> None:
        """Sends what the runs wrote since the last push: new points, or the whole chart when its curves changed."""
        assert self._widget is not None
        layout = self._current_layout()
        if layout != self._layout or self._resync.is_set():
            self._resync.clear()
            spec = self._full_spec()
            unchanged = spec == self._widget.spec
            # Set even when equal: appends extend this spec's points.
            self._widget.spec = spec
            if unchanged:
                # Setting an equal value sends nothing, but the view that asked still needs it.
                self._widget.send_state("spec")
            return
        items = []
        for tag, slots in layout:
            for key, _label, _color, run_ids in slots:
                for run_id in run_ids:
                    series = self._series[(tag, run_id)]
                    points = wire_points(self._experiment._points(run_id, tag, len(series)))
                    if points:
                        items.append({"tag": tag, "key": key, "run": run_id, "start": len(series), "points": points})
                        series.extend(points)
        if items:
            self._widget.send({"type": "append", "items": items})

    def _save(self) -> None:
        self.chart = Chart(chart_spec(self._experiment, self.tags, **self._options))
        # The update reaches only the frontend session that showed the chart. The widget stays open, so a
        # session opened since (a page reloaded) still draws every point; it closes when the cell runs again.
        if self._handle is not None:
            self._handle.update(self.chart)
        # After the update, so the session that showed the chart has dropped the widget's view by then.
        if self._widget is not None:
            self._widget.saved = True


def _cell_id(shell: Any) -> str | None:
    # JupyterLab and VS Code send the id of the cell they run.
    get_parent = getattr(getattr(shell, "kernel", None), "get_parent", None)
    parent = get_parent() if callable(get_parent) else None
    return ((parent or {}).get("metadata") or {}).get("cellId")
