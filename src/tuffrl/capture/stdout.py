"""Copies what the training script prints into the run, while still printing it."""

from __future__ import annotations

import sys
import threading
from collections.abc import Callable
from typing import Any, TextIO


class _Tee:
    def __init__(self, original: TextIO, sink: Callable[[str], None]) -> None:
        self._original = original
        self._sink = sink

    def write(self, text: str) -> int:
        written = self._original.write(text)
        if text:
            self._sink(text)
        return written

    def flush(self) -> None:
        self._original.flush()

    def __getattr__(self, name: str) -> Any:  # isatty, fileno, encoding, ...
        return getattr(self._original, name)


class OutputCapture:
    """Replaces ``sys.stdout`` and ``sys.stderr`` with tees until ``stop``.

    Only output written through Python's streams is captured: a C extension or a subprocess
    writing to the file descriptor directly is not.
    """

    def __init__(self, emit: Callable[[str, str], None], *, interval: float = 1.0) -> None:
        self._emit = emit
        self._interval = interval
        self._buffers: dict[str, list[str]] = {"stdout": [], "stderr": []}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._originals = (sys.stdout, sys.stderr)
        sys.stdout = _Tee(sys.stdout, lambda text: self._append("stdout", text))  # type: ignore[assignment]
        sys.stderr = _Tee(sys.stderr, lambda text: self._append("stderr", text))  # type: ignore[assignment]
        self._thread = threading.Thread(target=self._run, name="tuffrl-output", daemon=True)
        self._thread.start()

    def _append(self, stream: str, text: str) -> None:
        with self._lock:
            self._buffers[stream].append(text)

    def flush(self) -> None:
        with self._lock:
            batches = {name: "".join(parts) for name, parts in self._buffers.items() if parts}
            for parts in self._buffers.values():
                parts.clear()
        for stream, text in batches.items():
            self._emit(stream, text)

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            self.flush()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)
        if isinstance(sys.stdout, _Tee):
            sys.stdout = self._originals[0]
        if isinstance(sys.stderr, _Tee):
            sys.stderr = self._originals[1]
        self.flush()
