"""Finding runs in a log directory and following their event files as they grow."""

from __future__ import annotations

import os

from .records import CorruptRecordError, RecordReader
from .schema import Event, parse_event


def is_event_file(name: str) -> bool:
    return "tfevents" in name and not name.endswith((".tmp", ".lock"))


def discover_runs(logdir: str) -> dict[str, list[str]]:
    """Every directory under ``logdir`` holding event files is a run, named by its relative path.

    Hidden directories are skipped, which is where the board keeps its own state.
    """
    runs: dict[str, list[str]] = {}
    root = os.path.abspath(logdir)
    if not os.path.isdir(root):
        return runs
    for current, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        event_files = sorted(f for f in files if is_event_file(f))
        if event_files:
            rel = os.path.relpath(current, root)
            name = "." if rel == "." else rel.replace(os.sep, "/")
            runs[name] = [os.path.join(current, f) for f in event_files]
    return runs


class RunReader:
    """Follows every event file of one run; ``poll`` returns the events written since the last call."""

    def __init__(self, files: list[str] | None = None) -> None:
        self._readers: dict[str, RecordReader] = {}
        self._broken: set[str] = set()
        for path in files or []:
            self.add_file(path)

    def add_file(self, path: str) -> None:
        if path not in self._readers:
            self._readers[path] = RecordReader(path)

    @property
    def files(self) -> list[str]:
        return sorted(self._readers)

    def poll(self) -> list[Event]:
        events: list[Event] = []
        for path in sorted(self._readers):
            if path in self._broken:
                continue
            reader = self._readers[path]
            try:
                size = os.path.getsize(path)
            except OSError:
                continue
            if size <= reader.offset:
                continue
            try:
                records = reader.read_available()
            except CorruptRecordError:
                # A damaged file stops being read rather than taking the board down;
                # what was read before the damage stays.
                self._broken.add(path)
                continue
            for record in records:
                try:
                    events.append(parse_event(record))
                except ValueError:
                    continue
        return events
