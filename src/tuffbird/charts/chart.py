"""The board's chart as one HTML output: its script and data travel inside it, so it opens offline, and
a picture inside it stands in wherever scripts do not run (an untrusted notebook, a viewer, a converter).
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import html
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .. import __version__
from ..experiment import BY_DIRECTORY, as_tags

if TYPE_CHECKING:
    import os
    from collections.abc import Sequence

    from ..experiment import Experiment, GroupBy

STATIC_DIR = Path(__file__).resolve().parent / "static"
BUNDLE_PATH = STATIC_DIR / "widget.js"
SPEC_VERSION = 1
# Saved charts thin a run with more points than this to every k-th point, as TensorBoard samples its
# own charts; a live chart keeps every point, as the board does.
MAX_POINTS = 5000
# The picture's width in CSS pixels. It is drawn at 1.5x, so it stays sharp on HiDPI screens.
PNG_WIDTH = 640

# Runs in the page as a classic script, so it can find the output it belongs to. Every chart on a page
# unpacks the script once; if anything fails, the picture stays.
_LOADER = """(function () {
  var script = document.currentScript, root = script && script.parentNode;
  if (!root || root.hasAttribute('data-mounted')) return;
  root.setAttribute('data-mounted', '');
  var code = root.querySelector('.tuffbird-chart__code'), sha = code.getAttribute('data-sha');
  var charts = window.__tuffbirdCharts || (window.__tuffbirdCharts = {});
  if (!charts[sha]) charts[sha] = unpack(code.textContent);
  charts[sha].then(function (chart) {
    chart.mount(root, JSON.parse(root.querySelector('.tuffbird-chart__spec').textContent));
    var picture = root.querySelector('.tuffbird-chart__picture');
    if (picture) picture.remove();
  }).catch(function (error) {
    delete charts[sha];
    root.removeAttribute('data-mounted');
    console.warn('tuff-bird: the interactive chart did not load, so its picture stays', error);
  });
  function unpack(text) {
    var bytes = Uint8Array.from(atob(text.trim()), function (c) { return c.charCodeAt(0); });
    var stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));
    return new Response(stream).text().then(function (source) {
      var url = URL.createObjectURL(new Blob([source], { type: 'text/javascript' }));
      return import(url).catch(function () {
        return import('data:text/javascript;charset=utf-8,' + encodeURIComponent(source));
      }).finally(function () { URL.revokeObjectURL(url); });
    });
  }
})();"""

_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="generator" content="tuff-bird {version}">
<title>{title}</title>
<style>
  body {{ margin: 0; padding: 32px 24px; background: #f2f3f5; }}
  main {{ max-width: 1120px; margin: 0 auto; }}
  @media (prefers-color-scheme: dark) {{ body {{ background: #0a0a0a; color: #e5eaf3; }} }}
</style>
</head>
<body>
<main>
<noscript>This chart needs JavaScript.</noscript>
{chart}
</main>
</body>
</html>
"""


@dataclass(frozen=True)
class Bundle:
    """The chart's script: Vue, the TuffEx chart and their styles, as one ES module."""

    source: str
    #: gzip, then base64: about a third of the source.
    packed: str
    sha: str


_bundle: tuple[tuple[int, int], Bundle] | None = None


def bundle() -> Bundle:
    """The built chart script, read again when the file changes."""
    global _bundle
    try:
        stat = BUNDLE_PATH.stat()
    except FileNotFoundError:
        raise FileNotFoundError(f"the chart's script is missing at {BUNDLE_PATH}; run `pnpm install && pnpm build` in web/") from None
    stamp = (stat.st_mtime_ns, stat.st_size)
    if _bundle is None or _bundle[0] != stamp:
        raw = BUNDLE_PATH.read_bytes()
        packed = base64.b64encode(gzip.compress(raw, mtime=0)).decode("ascii")
        _bundle = (stamp, Bundle(raw.decode("utf-8"), packed, hashlib.sha256(raw).hexdigest()[:12]))
    return _bundle[1]


def chart_spec(
    experiment: Experiment,
    tags: str | Sequence[str],
    *,
    group_by: GroupBy = BY_DIRECTORY,
    smoothing: float = 0.6,
    show_raw: bool = True,
    log_x: bool = False,
    height: int | None = None,
    title: str | None = None,
    max_points: int | None = MAX_POINTS,
) -> dict[str, Any]:
    """What the chart draws, as JSON: a panel per tag, each with its curves and their runs' points.

    The page smooths and aggregates as the board does: a group is the mean of its smoothed runs
    with a one-standard-deviation band. ``group_by`` is as in :meth:`Experiment.curves`.
    """
    tags = as_tags(tags)
    panels = []
    for tag in tags:
        curves = [
            {
                "key": curve.key,
                "name": curve.label,
                "color": curve.color,
                "runs": [{"id": run_id, "points": wire_points(_thin(points, max_points))} for run_id, points in curve.runs.items()],
            }
            for curve in experiment.curves(tag, group_by)
        ]
        panels.append({"tag": tag, "curves": curves})
    return {
        "version": SPEC_VERSION,
        "title": title or "",
        "smoothing": smoothing,
        "showRaw": show_raw,
        "logX": log_x,
        "height": height or (300 if len(tags) == 1 else 240),
        "panels": panels,
    }


def wire_points(points: Sequence[tuple[float, float]]) -> list[list[Any]]:
    """Points for JSON: values to float32's seven digits, and NaN or infinity as strings the page reads back."""
    return [[step, _wire_value(value)] for step, value in points]


def _wire_value(value: float) -> float | str:
    if math.isfinite(value):
        return float(f"{value:.7g}")
    if value != value:
        return "NaN"
    return "Infinity" if value > 0 else "-Infinity"


def _thin(points: list[tuple[float, float]], max_points: int | None) -> list[tuple[float, float]]:
    if not max_points or len(points) <= max_points:
        return points
    stride = math.ceil(len(points) / max_points)
    thinned = points[::stride]
    if (len(points) - 1) % stride:
        thinned.append(points[-1])
    return thinned


class Chart:
    """The board's interactive chart. In a notebook it is the cell's output; :meth:`save` writes a page."""

    def __init__(self, spec: dict[str, Any]) -> None:
        self.spec = spec
        self._png: bytes | None = None

    def __repr__(self) -> str:
        tags = ", ".join(panel["tag"] for panel in self.spec["panels"])
        curves = len({curve["key"] for panel in self.spec["panels"] for curve in panel["curves"]})
        return f"<Chart of {tags}: {curves} curves>"

    def png(self) -> bytes | None:
        """The chart as a picture, drawn with matplotlib; ``None`` when it is not installed."""
        if self._png is None:
            try:
                from ..figures import chart_png
            except ImportError:
                self._png = b""
            else:
                self._png = chart_png(self.spec, width=PNG_WIDTH / 100, dpi=150)
        return self._png or None

    def to_html(self) -> str:
        """A whole page that opens offline, with the chart's script and data inside it."""
        title = self.spec.get("title") or ", ".join(panel["tag"] for panel in self.spec["panels"])
        return _PAGE.format(version=__version__, title=html.escape(title), chart=self._fragment(None))

    def save(self, path: str | os.PathLike[str]) -> Path:
        """Writes :meth:`to_html` to ``path`` (``.html``); figures for papers come from ``Experiment.plot``."""
        target = Path(path)
        if target.suffix.lower() not in (".html", ".htm"):
            raise ValueError(f"a chart saves as .html, not {target.suffix or 'a file without a suffix'}; for PDF, SVG or PNG use experiment.plot(...).savefig(path)")
        target.write_text(self.to_html(), encoding="utf-8")
        return target

    def _repr_mimebundle_(self, include: Any = None, exclude: Any = None) -> tuple[dict[str, Any], dict[str, Any]]:  # noqa: ARG002
        png = self.png()
        data: dict[str, Any] = {"text/html": self._fragment(png), "text/plain": repr(self)}
        metadata: dict[str, Any] = {}
        if png:
            data["image/png"] = base64.b64encode(png).decode("ascii")
            metadata["image/png"] = {"width": PNG_WIDTH}
        return data, metadata

    def _fragment(self, png: bytes | None) -> str:
        code = bundle()
        # "<" never appears outside a JSON string, and inside one it can be escaped, so no tag can close early.
        spec = json.dumps(self.spec, separators=(",", ":"), allow_nan=False).replace("<", "\\u003c")
        parts = ['<div class="tuffbird-chart">']
        if png:
            alt = html.escape(f"{repr(self)[1:-1]}, as a picture")
            parts.append(
                f'<img class="tuffbird-chart__picture" src="data:image/png;base64,{base64.b64encode(png).decode("ascii")}" '
                f'width="{PNG_WIDTH}" alt="{alt}" style="max-width:100%;height:auto">'
            )
        parts.append(f'<script type="application/json" class="tuffbird-chart__spec">{spec}</script>')
        parts.append(f'<script type="application/octet-stream" class="tuffbird-chart__code" data-sha="{code.sha}">{code.packed}</script>')
        parts.append(f"<script>{_LOADER}</script></div>")
        return "".join(parts)
