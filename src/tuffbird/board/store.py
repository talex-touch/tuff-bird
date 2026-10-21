"""Everything the board knows about a log directory, kept current by polling its event files."""

from __future__ import annotations

import contextlib
import os
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from ..events.reader import RunReader, discover_runs
from ..events.schema import HParamsEnd, HParamsStart, Media, Scalar, Text

# A run that has written nothing for this long and never wrote an end record is shown as idle:
# finished by a writer that does not record an end (Stable-Baselines3, SummaryWriter), or stopped.
IDLE_AFTER_SECS = 60.0
# How many deltas a reconnecting browser can catch up on before it has to reload everything.
DELTA_HISTORY = 20_000


@dataclass
class RunState:
    id: str
    reader: RunReader
    scalars: dict[str, list[list[float]]] = field(default_factory=dict)
    texts: dict[str, list[list[Any]]] = field(default_factory=dict)
    media: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    hparams: dict[str, Any] = field(default_factory=dict)
    group: str = ""
    start_time: float | None = None
    end_time: float | None = None
    end_status: str | None = None
    first_wall: float | None = None
    last_wall: float | None = None
    last_write: float = 0.0
    status: str = "running"

    def meta(self) -> dict[str, Any]:
        parent, _, leaf = self.id.rpartition("/")
        return {
            "id": self.id,
            "name": leaf or self.id,
            "parent": parent,
            "group": self.group or parent,
            "status": self.status,
            "startTime": self.start_time or self.first_wall,
            "endTime": self.end_time,
            "lastWall": self.last_wall,
            "lastWrite": self.last_write,
            "hparams": self.hparams,
            "scalarTags": sorted(self.scalars),
            "textTags": sorted(self.texts),
            "mediaTags": sorted(self.media),
            "files": [os.path.basename(path) for path in self.reader.files],
        }


class Store:
    def __init__(self, logdir: str) -> None:
        self.logdir = os.path.abspath(logdir)
        self.runs: dict[str, RunState] = {}
        # Sequence numbers only mean something within one board process; a page that reconnects
        # to a restarted board sees a different id and reloads instead of resuming.
        self.instance = uuid.uuid4().hex[:12]
        self.seq = 0
        self._deltas: deque[dict[str, Any]] = deque(maxlen=DELTA_HISTORY)
        # One re-entrant lock covers the runs and the delta log, so a snapshot and its sequence
        # number always describe the same state.
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)

    # ------------------------------------------------------------------ polling

    def scan(self) -> None:
        with self._lock:
            self._scan()

    def _scan(self) -> None:
        now = time.time()
        found = discover_runs(self.logdir)
        pending: list[dict[str, Any]] = []
        for run_id, files in found.items():
            state = self.runs.get(run_id)
            is_new = state is None
            if state is None:
                state = RunState(id=run_id, reader=RunReader())
                self.runs[run_id] = state
            for path in files:
                state.reader.add_file(path)
                with contextlib.suppress(OSError):
                    state.last_write = max(state.last_write, os.path.getmtime(path))
            changed = self._apply(state, state.reader.poll(), pending)
            status = self._status(state, now)
            if status != state.status:
                state.status = status
                changed = True
            if is_new or changed:
                pending.insert(0, {"type": "run", "run": state.meta()})
        if pending:
            self._publish(pending)

    def _status(self, state: RunState, now: float) -> str:
        if state.end_status:
            return {"success": "finished", "failure": "failed", "unknown": "stopped"}.get(state.end_status, state.end_status)
        return "running" if now - state.last_write < IDLE_AFTER_SECS else "idle"

    def _apply(self, state: RunState, events: list[Any], pending: list[dict[str, Any]]) -> bool:
        """Folds new events into ``state``; returns whether the run's metadata changed."""
        changed = False
        points: dict[str, list[list[float]]] = {}
        texts: dict[str, list[list[Any]]] = {}
        for event in events:
            if event.wall_time:
                state.first_wall = event.wall_time if state.first_wall is None else min(state.first_wall, event.wall_time)
                state.last_wall = event.wall_time if state.last_wall is None else max(state.last_wall, event.wall_time)
            for value in event.values:
                if isinstance(value, Scalar):
                    if value.tag not in state.scalars:
                        state.scalars[value.tag] = []
                        changed = True
                    point = [event.step, value.value, event.wall_time]
                    state.scalars[value.tag].append(point)
                    points.setdefault(value.tag, []).append(point)
                elif isinstance(value, Text):
                    if value.tag not in state.texts:
                        state.texts[value.tag] = []
                        changed = True
                    item = [event.step, event.wall_time, value.text]
                    state.texts[value.tag].append(item)
                    texts.setdefault(value.tag, []).append(item)
                elif isinstance(value, HParamsStart):
                    state.hparams = value.hparams
                    state.group = value.group
                    state.start_time = value.start_time or event.wall_time
                    changed = True
                elif isinstance(value, HParamsEnd):
                    state.end_status = value.status
                    state.end_time = value.end_time or event.wall_time
                    changed = True
                elif isinstance(value, Media):
                    if value.tag not in state.media:
                        state.media[value.tag] = []
                        changed = True
                    state.media[value.tag].append({
                        "step": event.step, "wall": event.wall_time, "kind": value.kind,
                        "contentType": value.content_type, "bytes": len(value.data), **value.meta,
                    })
        for tag, batch in points.items():
            pending.append({"type": "scalars", "run": state.id, "tag": tag, "points": batch})
        for tag, batch in texts.items():
            pending.append({"type": "text", "run": state.id, "tag": tag, "items": batch})
        return changed

    def _publish(self, deltas: list[dict[str, Any]]) -> None:
        with self._cond:
            for delta in deltas:
                self.seq += 1
                delta["seq"] = self.seq
                self._deltas.append(delta)
            self._cond.notify_all()

    # ------------------------------------------------------------------ reading

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "board": self.instance,
                "seq": self.seq,
                "logdir": self.logdir,
                "runs": [state.meta() for state in self.runs.values()],
                "scalars": {
                    run_id: {tag: list(points) for tag, points in state.scalars.items()}
                    for run_id, state in self.runs.items()
                },
                "texts": {
                    run_id: {tag: list(items) for tag, items in state.texts.items()}
                    for run_id, state in self.runs.items()
                },
            }

    def wait_deltas(self, since: int, timeout: float) -> list[dict[str, Any]] | None:
        """Deltas after ``since``, waiting up to ``timeout``; ``None`` when ``since`` is too old to resume."""
        with self._cond:
            if since > self.seq or since < self.seq - len(self._deltas):
                return None
            if self.seq <= since:
                self._cond.wait(timeout)
            if since < self.seq - len(self._deltas):
                return None
            return [delta for delta in self._deltas if delta["seq"] > since]
