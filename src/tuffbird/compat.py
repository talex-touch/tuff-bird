"""A ``SummaryWriter`` with the methods of PyTorch's, so existing scripts only change the import."""

from __future__ import annotations

import os
import socket
import time
from collections.abc import Mapping
from typing import Any

from .board.launch import ensure_board
from .events import EventFileWriter
from .events.schema import hparams_end_event, hparams_start_event, scalars_event, text_event
from .run import _as_number, _config_value, _flatten, _is_rank_zero


class SummaryWriter:
    """Covers ``add_scalar``, ``add_scalars``, ``add_text``, ``add_hparams``, ``flush`` and ``close``.

    Unlike PyTorch's, it starts the board for the parent log directory (``board=False`` turns
    that off), and ``add_scalars`` writes ``main_tag/key`` tags into the same run instead of one
    run per key.
    """

    def __init__(
        self,
        log_dir: str | None = None,
        comment: str = "",
        purge_step: int | None = None,  # noqa: ARG002 - accepted for signature compatibility
        max_queue: int = 10,  # noqa: ARG002
        flush_secs: float = 1.0,
        filename_suffix: str = "",  # noqa: ARG002
        *,
        board: bool = True,
        open_browser: bool | None = None,
    ) -> None:
        if log_dir is None:
            stamp = time.strftime("%b%d_%H-%M-%S")
            log_dir = os.path.join("runs", f"{stamp}_{socket.gethostname()}{comment}")
        self.log_dir = log_dir
        self._writer = EventFileWriter(log_dir, flush_secs=flush_secs)
        self.board_url: str | None = None
        if board and os.environ.get("TUFFBIRD_BOARD", "1") != "0" and _is_rank_zero():
            self.board_url = ensure_board(os.path.dirname(os.path.abspath(log_dir)), open_browser=open_browser)

    def add_scalar(self, tag: str, scalar_value: Any, global_step: int | None = None, walltime: float | None = None, **_: Any) -> None:
        number = _as_number(scalar_value)
        if number is not None:
            self._writer.add(scalars_event(int(global_step or 0), walltime or time.time(), {tag: number}))

    def add_scalars(self, main_tag: str, tag_scalar_dict: Mapping[str, Any], global_step: int | None = None, walltime: float | None = None) -> None:
        numbers = {}
        for key, value in tag_scalar_dict.items():
            number = _as_number(value)
            if number is not None:
                numbers[f"{main_tag}/{key}"] = number
        if numbers:
            self._writer.add(scalars_event(int(global_step or 0), walltime or time.time(), numbers))

    def add_text(self, tag: str, text_string: str, global_step: int | None = None, walltime: float | None = None) -> None:
        self._writer.add(text_event(int(global_step or 0), walltime or time.time(), tag, text_string))

    def add_hparams(self, hparam_dict: Mapping[str, Any], metric_dict: Mapping[str, Any], *_: Any, **__: Any) -> None:
        now = time.time()
        hparams = {key: _config_value(value) for key, value in _flatten(hparam_dict).items()}
        self._writer.add(hparams_start_event(now, hparams))
        metrics = {key: n for key, value in metric_dict.items() if (n := _as_number(value)) is not None}
        if metrics:
            self._writer.add(scalars_event(0, now, metrics))
        self._writer.add(hparams_end_event(now, "success"))

    def flush(self) -> None:
        self._writer.flush()

    def close(self) -> None:
        self._writer.close()

    def __enter__(self) -> SummaryWriter:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
