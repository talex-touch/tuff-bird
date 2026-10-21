"""The file in a log directory that says which board is serving it."""

from __future__ import annotations

import contextlib
import json
import os
from typing import Any

STATE_DIR = ".tuffrl"
LOCK_NAME = "board.json"


def lock_path(logdir: str) -> str:
    return os.path.join(os.path.abspath(logdir), STATE_DIR, LOCK_NAME)


def read_lock(logdir: str) -> dict[str, Any] | None:
    try:
        with open(lock_path(logdir), encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def write_lock(logdir: str, data: dict[str, Any]) -> None:
    path = lock_path(logdir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = f"{path}.{os.getpid()}.tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(data, handle)
    os.replace(temporary, path)  # readers see the old file or the new one, never half of one


def clear_lock(logdir: str, pid: int) -> None:
    data = read_lock(logdir)
    if data and data.get("pid") == pid:
        with contextlib.suppress(OSError):
            os.remove(lock_path(logdir))
