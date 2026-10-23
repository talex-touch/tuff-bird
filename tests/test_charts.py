"""The board's chart as one HTML output: the data it draws, and the page or notebook output that carries it."""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
import sys

import pytest
from helpers import logged_run, quiet_run, spec_in

import tuffbird
from tuffbird.charts import Chart, chart_spec
from tuffbird.charts import chart as chart_module
from tuffbird.charts.chart import bundle, wire_points


@pytest.fixture
def experiment(tmp_path):
    """Two seeds in one directory, each logging two tags."""
    for seed in (1, 2):
        run = quiet_run(tmp_path, f"seed-{seed}", group="sac")
        for step in range(3):
            run.log({"loss": float(seed + step), "eval/return": float(-step)}, step=step)
        run.finish()
    return tuffbird.load(tmp_path)


def test_a_spec_has_a_panel_per_tag_with_each_curves_runs(experiment):
    spec = chart_spec(experiment, ["loss", "eval/return"], smoothing=0.3, show_raw=False, log_x=True, title="SAC")
    assert {key: value for key, value in spec.items() if key != "panels"} == {
        "version": 1, "title": "SAC", "smoothing": 0.3, "showRaw": False, "logX": True, "height": 240,
    }
    assert [panel["tag"] for panel in spec["panels"]] == ["loss", "eval/return"]
    (curve,) = spec["panels"][0]["curves"]
    assert (curve["key"], curve["name"]) == ("group:sac", "sac")
    assert curve["runs"] == [
        {"id": "sac/seed-1", "points": [[0, 1.0], [1, 2.0], [2, 3.0]]},
        {"id": "sac/seed-2", "points": [[0, 2.0], [1, 3.0], [2, 4.0]]},
    ]
    assert chart_spec(experiment, "loss")["height"] == 300


def test_a_saved_chart_keeps_every_kth_point_of_a_long_run_and_its_last(tmp_path):
    logged_run(tmp_path, "run", [(step, float(step)) for step in range(12)])
    experiment = tuffbird.load(tmp_path)

    def steps(max_points):
        return [point[0] for point in chart_spec(experiment, "loss", max_points=max_points)["panels"][0]["curves"][0]["runs"][0]["points"]]

    assert steps(5) == [0, 3, 6, 9, 11]
    assert steps(None) == list(range(12))


def test_points_travel_as_json_with_seven_digits_and_named_infinities():
    points = wire_points([(0, 0.1234567891), (1, float("nan")), (2, float("inf")), (3, float("-inf")), (4, 12345678.9)])
    assert points == [[0, 0.1234568], [1, "NaN"], [2, "Infinity"], [3, "-Infinity"], [4, 12345680.0]]
    json.dumps(points, allow_nan=False)


def test_the_script_travels_gzipped_and_is_read_again_when_it_changes(chart_script):
    first = bundle()
    assert gzip.decompress(base64.b64decode(first.packed)).decode("utf-8") == first.source == chart_script.read_text(encoding="utf-8")
    assert first.sha == hashlib.sha256(chart_script.read_bytes()).hexdigest()[:12]
    assert bundle() is first
    chart_script.write_text("export function mount(root) { root.textContent = 'chart' }\n", encoding="utf-8")
    assert bundle().source != first.source


def test_a_missing_script_says_how_to_build_it(tmp_path, monkeypatch):
    monkeypatch.setattr(chart_module, "BUNDLE_PATH", tmp_path / "widget.js")
    monkeypatch.setattr(chart_module, "_bundle", None)
    with pytest.raises(FileNotFoundError, match="pnpm build"):
        bundle()


@pytest.mark.usefixtures("chart_script")
def test_no_tag_or_title_can_close_the_page_early(tmp_path):
    tag = "a</script><b>"
    logged_run(tmp_path, "run", [(0, 1.0)], tag=tag)
    page = tuffbird.load(tmp_path).chart(tag, title="<loss & co>").to_html()
    assert "<title>&lt;loss &amp; co&gt;</title>" in page
    # The data, the packed script and the loader.
    assert page.count("</script>") == 3
    spec = spec_in(page)
    assert (spec["title"], spec["panels"][0]["tag"]) == ("<loss & co>", tag)
    assert f'data-sha="{bundle().sha}"' in page


@pytest.mark.usefixtures("chart_script")
def test_save_writes_a_page_and_sends_figures_to_plot(experiment, tmp_path):
    chart = experiment.chart("loss")
    assert repr(chart) == "<Chart of loss: 1 curves>"
    path = chart.save(tmp_path / "loss.html")
    assert path.read_text(encoding="utf-8").startswith("<!doctype html>")
    with pytest.raises(ValueError, match=r"experiment\.plot"):
        chart.save(tmp_path / "loss.pdf")
    with pytest.raises(ValueError, match="logged missing"):
        experiment.chart("missing")


@pytest.mark.usefixtures("chart_script")
def test_in_a_notebook_the_chart_carries_a_picture_for_viewers_that_run_no_scripts(experiment):
    pytest.importorskip("matplotlib")
    data, metadata = experiment.chart("loss")._repr_mimebundle_()
    assert sorted(data) == ["image/png", "text/html", "text/plain"]
    assert metadata == {"image/png": {"width": 640}}
    assert 'class="tuffbird-chart__picture"' in data["text/html"]
    png = base64.b64decode(data["image/png"])
    # 640 CSS pixels drawn at 1.5x.
    assert png.startswith(b"\x89PNG") and int.from_bytes(png[16:20], "big") == 960


@pytest.mark.usefixtures("chart_script")
def test_without_matplotlib_the_chart_has_no_picture(experiment, monkeypatch):
    monkeypatch.setitem(sys.modules, "tuffbird.figures", None)
    data, metadata = experiment.chart("loss")._repr_mimebundle_()
    assert sorted(data) == ["text/html", "text/plain"]
    assert metadata == {}
    assert 'class="tuffbird-chart__picture"' not in data["text/html"]
    assert spec_in(data["text/html"]) == Chart(chart_spec(experiment, "loss")).spec
