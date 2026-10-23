"""The chart in a notebook while runs write: what the widget is sent, and the chart saved when they stop."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from helpers import logged_run, quiet_run

import tuffbird

pytest.importorskip("anywidget")
from tuffbird.charts import Chart, live  # noqa: E402


def widget_for(logdir):
    """A live chart of ``loss`` with its widget, pushed to by the test instead of by its thread."""
    chart = live.Live(tuffbird.load(logdir), ["loss"], {}, interval=0.01)
    chart._widget = live.ChartWidget(_esm="", spec=chart._full_spec())
    sent = SimpleNamespace(messages=[], states=[])

    def send_state(key=None):
        sent.states.append(key)

    chart._widget.send = sent.messages.append
    chart._widget.send_state = send_state
    return chart, sent


def points_of(chart, run_id):
    return next(run["points"] for curve in chart._widget.spec["panels"][0]["curves"] for run in curve["runs"] if run["id"] == run_id)


@pytest.fixture
def notebook(monkeypatch):
    """A kernel for show(): what it displays lands in the list."""
    shown = []
    monkeypatch.setattr(live, "get_ipython", object)
    monkeypatch.setattr(live, "display", lambda value, **_options: shown.append(value))
    yield shown
    for chart in list(live._shown.values()):
        chart.cancel()
    live._shown.clear()


def test_new_points_go_out_as_appends_that_extend_the_kernels_spec(tmp_path):
    run = quiet_run(tmp_path, "run")
    run.log({"loss": 1.0}, step=0)
    run.flush()
    chart, sent = widget_for(tmp_path)

    run.log({"loss": 0.5}, step=1)
    run.flush()
    chart._experiment.refresh()
    chart._push()
    chart._push()
    assert sent.messages == [{"type": "append", "items": [{"tag": "loss", "key": "run", "run": "run", "start": 1, "points": [[1, 0.5]]}]}]
    # A view restored after a reload starts from the spec, so it holds the appended points too.
    assert points_of(chart, "run") == [[0, 1.0], [1, 0.5]]
    assert sent.states == []
    run.finish()


def test_a_new_run_sends_the_whole_chart(tmp_path):
    logged_run(tmp_path, "seed-1", [(0, 1.0)], group="sac")
    chart, sent = widget_for(tmp_path)

    logged_run(tmp_path, "seed-2", [(0, 3.0)], group="sac")
    chart._experiment.refresh()
    chart._push()
    assert sent.messages == []
    assert sent.states == ["spec"]
    assert points_of(chart, "sac/seed-2") == [[0, 3.0]]


def test_a_view_that_missed_points_is_sent_the_chart_again_even_when_it_has_not_changed(tmp_path):
    run = quiet_run(tmp_path, "run")
    run.log({"loss": 1.0}, step=0)
    run.flush()
    chart, sent = widget_for(tmp_path)

    chart._on_message(chart._widget, {"type": "something else"}, [])
    chart._push()
    assert sent.states == []
    chart._on_message(chart._widget, {"type": "sync"}, [])
    chart._push()
    # Assigning an equal spec sends nothing by itself.
    assert sent.states == ["spec"]

    # Appends go on extending the spec the view was sent.
    run.log({"loss": 0.5}, step=1)
    run.flush()
    chart._experiment.refresh()
    chart._push()
    assert [item["start"] for item in sent.messages[-1]["items"]] == [1]
    assert points_of(chart, "run") == [[0, 1.0], [1, 0.5]]
    run.finish()


def test_saving_replaces_the_output_and_then_tells_the_widget(tmp_path):
    logged_run(tmp_path, "run", [(0, 1.0)])
    chart, _ = widget_for(tmp_path)
    updates = []
    chart._handle = SimpleNamespace(update=lambda value: updates.append((value, chart._widget.saved)))
    chart._save()
    assert updates == [(chart.chart, False)]
    assert isinstance(chart.chart, Chart)
    assert chart._widget.saved


@pytest.mark.usefixtures("chart_script")
def test_once_every_run_has_stopped_the_chart_is_saved(tmp_path, monkeypatch):
    monkeypatch.setattr(live, "SETTLE_SECS", 0)
    logged_run(tmp_path, "run", [(0, 1.0)])
    chart = live.Live(tuffbird.load(tmp_path), ["loss"], {}, interval=0.01)
    chart._start()
    chart._thread.join(timeout=10)
    assert repr(chart) == "<Live chart of loss: saved>"
    assert chart._widget.saved
    chart.cancel()


def test_show_outside_a_notebook_says_to_save_the_chart(tmp_path):
    logged_run(tmp_path, "run", [(0, 1.0)])
    with pytest.raises(RuntimeError, match=r"\.save\('chart\.html'\)"):
        tuffbird.load(tmp_path).show("loss")


def test_with_every_run_stopped_show_displays_the_saved_chart(tmp_path, notebook):
    logged_run(tmp_path, "run", [(0, 1.0)])
    chart = tuffbird.load(tmp_path).show("loss")
    assert repr(chart) == "<Live chart of loss: saved>"
    assert notebook == [chart.chart]
    with pytest.raises(ValueError, match="logged missing"):
        tuffbird.load(tmp_path).show("missing")


@pytest.mark.usefixtures("chart_script")
def test_showing_a_cell_again_replaces_the_chart_it_was_following(tmp_path, notebook, monkeypatch):
    monkeypatch.setattr(live, "SETTLE_SECS", 60)
    logged_run(tmp_path, "run", [(0, 1.0)])
    experiment = tuffbird.load(tmp_path)
    first = experiment.show("loss", live=True, interval=0.01)
    assert first.following

    second = experiment.show("loss", live=True, interval=0.01)
    assert not first.following
    # Replaced, not saved: the cell's new output is the second chart.
    assert first.chart is None
    assert first._widget.comm is None
    assert second.following
    second.stop()
    assert repr(second) == "<Live chart of loss: saved>"
    assert len(notebook) == 2
