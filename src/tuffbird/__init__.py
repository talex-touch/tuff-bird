"""tuff-bird: training logs as TensorBoard event files, with a live local board that starts itself.

    import tuffbird
    run = tuffbird.init(logdir="logs", name="sac-seed1", group="sac", config={"lr": 3e-4})
    run.log({"train/loss": loss, "eval/return": ret}, step=step)
    run.finish()
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

__version__ = "0.2.0"

from .board import ensure_board  # noqa: E402 - needs __version__ above
from .compat import SummaryWriter  # noqa: E402
from .experiment import BY_DIRECTORY, Experiment, load  # noqa: E402
from .run import Run  # noqa: E402

_current: Run | None = None


def init(
    logdir: str = "logs",
    name: str | None = None,
    group: str | None = None,
    config: Mapping[str, Any] | None = None,
    **options: Any,
) -> Run:
    """Starts a run under ``logdir`` and, unless ``board=False``, the board that shows it."""
    global _current
    _current = Run(logdir=logdir, name=name, group=group, config=config, **options)
    return _current


def log(metrics: Mapping[str, Any], step: int | None = None) -> None:
    """Logs to the run started by :func:`init`."""
    if _current is None:
        raise RuntimeError("call tuffbird.init() first")
    _current.log(metrics, step=step)


def finish(status: str = "success") -> None:
    if _current is not None:
        _current.finish(status)


def board(logdir: str = "logs", **options: Any) -> str | None:
    """Opens (or finds) the board for a log directory, for runs written by any TensorBoard writer."""
    return ensure_board(logdir, **options)


__all__ = ["BY_DIRECTORY", "Experiment", "Run", "SummaryWriter", "__version__", "board", "finish", "init", "load", "log"]
