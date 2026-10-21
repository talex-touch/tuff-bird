"""A training run: one directory of TensorBoard event files, and the board that shows it."""

from __future__ import annotations

import atexit
import math
import os
import sys
import threading
import time
from collections.abc import Mapping
from typing import Any

from .board.launch import ensure_board
from .capture import OutputCapture, SystemSampler
from .events import EventFileWriter
from .events.schema import hparams_end_event, hparams_start_event, scalars_event, text_event


def _is_rank_zero() -> bool:
    """Under ``torch.distributed`` and friends only rank 0 starts the board."""
    for name in ("RANK", "LOCAL_RANK", "SLURM_PROCID"):
        value = os.environ.get(name)
        if value not in (None, "", "0"):
            return False
    return True


def _flatten(values: Mapping[str, Any], prefix: str = "", sep: str = "/") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, value in values.items():
        name = f"{prefix}{sep}{key}" if prefix else str(key)
        if isinstance(value, Mapping):
            flat.update(_flatten(value, name, sep))
        else:
            flat[name] = value
    return flat


def _as_number(value: Any) -> float | None:
    """Numbers, booleans, NumPy scalars and one-element tensors; ``None`` for anything else."""
    if isinstance(value, bool):
        return float(value)
    try:
        number = float(value)
    except (TypeError, ValueError):
        item = getattr(value, "item", None)
        if not callable(item):
            return None
        try:
            number = float(item())
        except (TypeError, ValueError, RuntimeError):
            return None
    return number


def _config_value(value: Any) -> Any:
    if isinstance(value, (bool, str)) or value is None:
        return value
    number = _as_number(value)
    if number is not None and math.isfinite(number):
        return int(number) if isinstance(value, int) else number
    return str(value)


class Run:
    """Logs one training run.

    Everything goes into one event file under ``<logdir>/<group>/<name>``: the metrics passed
    to :meth:`log`, the config as TensorBoard hparams, what the script prints, and system
    metrics under ``sys/``. TensorBoard can open the directory as it is.
    """

    def __init__(
        self,
        logdir: str = "logs",
        name: str | None = None,
        group: str | None = None,
        config: Mapping[str, Any] | None = None,
        *,
        board: bool = True,
        open_browser: bool | None = None,
        capture_output: bool = True,
        system_metrics: bool = True,
        system_interval: float = 5.0,
        flush_secs: float = 1.0,
    ) -> None:
        self.logdir = os.path.abspath(logdir)
        self.name = name or time.strftime("%Y%m%d-%H%M%S")
        self.group = group or ""
        parts = [part for part in (self.group.split("/") + self.name.split("/")) if part]
        self.dir = os.path.join(self.logdir, *parts)
        self.config = {key: _config_value(value) for key, value in _flatten(config or {}).items()}
        self.start_time = time.time()
        self._step = 0
        self._finished = False
        self._lock = threading.Lock()
        self._writer = EventFileWriter(self.dir, flush_secs=flush_secs)
        self._writer.add(hparams_start_event(self.start_time, self.config, self.group))
        self.board_url: str | None = None
        if board and os.environ.get("TUFFRL_BOARD", "1") != "0" and _is_rank_zero():
            self.board_url = ensure_board(self.logdir, open_browser=open_browser)
        self._output = OutputCapture(self._emit_output) if capture_output else None
        self._system = SystemSampler(self._emit_system, interval=system_interval) if system_metrics else None
        self._exit_status = "success"
        self._previous_excepthook = sys.excepthook
        sys.excepthook = self._excepthook
        atexit.register(self._finish_at_exit)

    # ------------------------------------------------------------------ logging

    @property
    def step(self) -> int:
        """The step the next :meth:`log` call without ``step`` uses."""
        return self._step

    def log(self, metrics: Mapping[str, Any], step: int | None = None) -> None:
        """Logs numeric values at ``step`` (the previous step plus one when omitted).

        Nested mappings become ``/``-separated tags; values that are not numbers are skipped.
        """
        with self._lock:
            if step is None:
                step = self._step
            self._step = int(step) + 1
        numbers = {}
        for tag, value in _flatten(metrics).items():
            number = _as_number(value)
            if number is not None:
                numbers[tag] = number
        if numbers:
            self._writer.add(scalars_event(int(step), time.time(), numbers))

    def log_text(self, tag: str, text: str, step: int | None = None) -> None:
        self._writer.add(text_event(self._step if step is None else int(step), time.time(), tag, text))

    def _emit_output(self, stream: str, text: str) -> None:
        if not self._finished:
            self._writer.add(text_event(self._step, time.time(), stream, text))

    def _emit_system(self, seconds: int, metrics: dict[str, float]) -> None:
        if metrics and not self._finished:
            self._writer.add(scalars_event(seconds, time.time(), metrics))

    # ------------------------------------------------------------------ lifecycle

    def flush(self) -> None:
        if self._output:
            self._output.flush()
        self._writer.flush()

    def finish(self, status: str = "success") -> None:
        """Writes the end record (``success`` or ``failure``) and closes the file."""
        if self._finished:
            return
        if self._system:
            self._system.stop()
        if self._output:
            self._output.stop()
        self._finished = True
        self._writer.add(hparams_end_event(time.time(), status))
        self._writer.close()

    @staticmethod
    def _status_for(exc_type: Any) -> str:
        if exc_type is None:
            return "success"
        if issubclass(exc_type, KeyboardInterrupt):
            return "unknown"  # stopped by hand: neither a success nor a failure
        return "failure"

    def _excepthook(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self._exit_status = self._status_for(exc_type)
        self._previous_excepthook(exc_type, exc, tb)

    def _finish_at_exit(self) -> None:
        self.finish(self._exit_status)

    def __enter__(self) -> Run:
        return self

    def __exit__(self, exc_type: Any, _exc: Any, _tb: Any) -> None:
        self.finish(self._status_for(exc_type))
