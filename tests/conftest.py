import os
import sys

import pytest

# The helpers module sits next to the tests; the package itself comes from the installed tuff-bird.
sys.path.insert(0, os.path.dirname(__file__))


@pytest.fixture
def chart_script(tmp_path, monkeypatch):
    """A stand-in for the chart's built script, which only ``pnpm build`` in web/ makes."""
    from tuffbird.charts import chart

    path = tmp_path / "widget.js"
    path.write_text("export function mount() {}\n", encoding="utf-8")
    monkeypatch.setattr(chart, "BUNDLE_PATH", path)
    monkeypatch.setattr(chart, "_bundle", None)
    return path
