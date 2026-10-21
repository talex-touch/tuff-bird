"""Appends events to a TensorBoard event file without holding up the training loop."""

from __future__ import annotations

import os
import socket
import threading
import time

from .records import encode_record
from .schema import file_version_event

_counter_lock = threading.Lock()
_counter = 0


def event_file_name() -> str:
    """``events.out.tfevents.<seconds>.<host>.<pid>.<n>``: the shape TensorBoard looks for."""
    global _counter
    with _counter_lock:
        _counter += 1
        count = _counter
    return f"events.out.tfevents.{int(time.time())}.{socket.gethostname()}.{os.getpid()}.{count}"


class EventFileWriter:
    """Queues encoded events and writes them from a background thread.

    ``add`` only appends to a list. The thread writes whatever is queued every
    ``flush_secs`` and calls ``flush`` on the file, so a reader polling the file sees new
    points within about that long; a crash loses at most the last interval. Records are
    written whole, so a reader never sees a torn one except at the very end of the file.
    """

    def __init__(self, run_dir: str, *, flush_secs: float = 1.0) -> None:
        os.makedirs(run_dir, exist_ok=True)
        self.path = os.path.join(run_dir, event_file_name())
        self._file = open(self.path, "ab")  # noqa: SIM115 - closed in close()
        self._pending: list[bytes] = [encode_record(file_version_event(time.time()))]
        self._lock = threading.Lock()
        self._io_lock = threading.Lock()  # one drain at a time keeps batches in order
        self._wake = threading.Event()
        self._closed = False
        self._flush_secs = flush_secs
        self._thread = threading.Thread(target=self._run, name="tuffrl-writer", daemon=True)
        self._thread.start()

    def add(self, event: bytes) -> None:
        record = encode_record(event)
        with self._lock:
            if self._closed:
                raise RuntimeError("event writer is closed")
            self._pending.append(record)

    def _drain(self) -> None:
        with self._io_lock:
            with self._lock:
                batch, self._pending = self._pending, []
            if batch:
                self._file.write(b"".join(batch))
                self._file.flush()

    def _run(self) -> None:
        while not self._closed:
            self._wake.wait(self._flush_secs)
            self._wake.clear()
            self._drain()

    def flush(self) -> None:
        self._drain()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._wake.set()
        self._thread.join(timeout=5)
        self._drain()
        self._file.close()
