"""Figures for papers, drawn with matplotlib: ``pip install "tuff-bird[plot]"``."""

try:
    import matplotlib  # noqa: F401
    import numpy  # noqa: F401
except ImportError as error:
    raise ImportError('figures need matplotlib and numpy: pip install "tuff-bird[plot]"') from error

from .plot import PaperFigure, caption, chart_png, plot  # noqa: E402
from .stats import Summary, smooth_ema, summarize  # noqa: E402

__all__ = ["PaperFigure", "Summary", "caption", "chart_png", "plot", "smooth_ema", "summarize"]
