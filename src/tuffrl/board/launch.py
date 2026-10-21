"""Starting the board from a training process, or finding the one already serving the log directory."""

from __future__ import annotations

import contextlib
import getpass
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from typing import Any

from .lock import STATE_DIR, lock_path, read_lock

DEFAULT_PORT = 6066
START_TIMEOUT_SECS = 10.0


def _healthy(info: dict[str, Any], logdir: str) -> bool:
    url = info.get("url")
    if not url:
        return False
    try:
        with urllib.request.urlopen(f"{url}/api/health", timeout=1.5) as response:  # noqa: S310 - local URL from our own lock
            health = json.load(response)
    except (OSError, ValueError):
        return False
    return bool(health.get("ok")) and os.path.abspath(health.get("logdir", "")) == os.path.abspath(logdir)


def is_remote_session() -> bool:
    return any(os.environ.get(name) for name in ("SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY"))


def can_open_browser() -> bool:
    override = os.environ.get("TUFFRL_OPEN_BROWSER")
    if override is not None:
        return override.strip().lower() not in ("0", "false", "no", "off", "")
    if is_remote_session() or os.environ.get("CI"):
        return False
    if sys.platform.startswith("linux") and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return False
    return True


def _spawn(logdir: str, host: str, port: int) -> None:
    state_dir = os.path.join(os.path.abspath(logdir), STATE_DIR)
    os.makedirs(state_dir, exist_ok=True)
    log = open(os.path.join(state_dir, "board.log"), "ab")  # noqa: SIM115 - handed to the child
    kwargs: dict[str, Any] = {"stdin": subprocess.DEVNULL, "stdout": log, "stderr": log, "close_fds": True}
    if os.name == "nt":  # pragma: no cover
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True  # the board outlives the training process
    subprocess.Popen(
        [sys.executable, "-m", "tuffrl", "board", os.path.abspath(logdir), "--host", host, "--port", str(port), "--no-browser"],
        **kwargs,
    )
    log.close()


def _claim_start(logdir: str) -> bool:
    """Only one of several processes starting at once launches the board; the rest wait for it."""
    path = f"{lock_path(logdir)}.starting"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        if time.time() - os.path.getmtime(path) > START_TIMEOUT_SECS * 2:
            os.remove(path)  # left behind by a launch that died
    except OSError:
        pass
    try:
        os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        return True
    except FileExistsError:
        return False


def _release_start(logdir: str) -> None:
    with contextlib.suppress(OSError):
        os.remove(f"{lock_path(logdir)}.starting")


def ensure_board(
    logdir: str,
    *,
    host: str = "127.0.0.1",
    port: int | None = None,
    open_browser: bool | None = None,
    announce: bool = True,
) -> str | None:
    """Returns the URL of the board serving ``logdir``, starting one when none is running."""
    port = port or int(os.environ.get("TUFFRL_BOARD_PORT", DEFAULT_PORT))
    host = os.environ.get("TUFFRL_BOARD_HOST", host)
    info = read_lock(logdir)
    started = False
    if not (info and _healthy(info, logdir)):
        claimed = _claim_start(logdir)
        try:
            if claimed:
                _spawn(logdir, host, port)
                started = True
            deadline = time.time() + START_TIMEOUT_SECS
            info = None
            while time.time() < deadline:
                candidate = read_lock(logdir)
                if candidate and _healthy(candidate, logdir):
                    info = candidate
                    break
                time.sleep(0.2)
        finally:
            if claimed:
                _release_start(logdir)
    if not info:
        if announce:
            print(f"[tuffrl] the board did not start; see {os.path.join(logdir, STATE_DIR, 'board.log')}", file=sys.stderr)
        return None
    url = str(info["url"])
    if announce:
        print(f"[tuffrl] board: {url}  (logdir {os.path.abspath(logdir)})", file=sys.stderr, flush=True)
        if is_remote_session():
            board_port = info.get("port")
            print(
                f"[tuffrl] from your own machine: ssh -N -L {board_port}:127.0.0.1:{board_port} "
                f"{getpass.getuser()}@{socket.gethostname()}  then open http://127.0.0.1:{board_port}",
                file=sys.stderr, flush=True,
            )
    if started and (can_open_browser() if open_browser is None else open_browser):
        webbrowser.open(url)
    return url


def stop_board(logdir: str) -> bool:
    info = read_lock(logdir)
    if not info or not info.get("pid"):
        return False
    try:
        os.kill(int(info["pid"]), 15)
    except OSError:
        return False
    return True
