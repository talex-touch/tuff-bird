"""The board process: started from a training script, found again, and stopped."""

from __future__ import annotations

import json
import os
import socket
import time
from urllib.request import urlopen

import pytest
from helpers import quiet_run

from tuffrl.board import ensure_board, stop_board
from tuffrl.board.lock import read_lock
from tuffrl.board.server import BoardHandler, _bind


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def fetch_json(url: str):
    with urlopen(url, timeout=5) as response:  # noqa: S310 - a local test server
        return json.load(response)


@pytest.fixture
def board(tmp_path):
    run = quiet_run(tmp_path, "run", config={"lr": 0.5})
    run.log({"loss": 0.5}, step=0)
    run.finish()
    url = ensure_board(str(tmp_path), port=free_port(), open_browser=False, announce=False)
    assert url, (tmp_path / ".tuffrl" / "board.log").read_text()
    yield url
    stop_board(str(tmp_path))
    deadline = time.time() + 5
    while read_lock(str(tmp_path)) and time.time() < deadline:
        time.sleep(0.1)


def test_board_serves_the_log_directory(board, tmp_path):
    health = fetch_json(f"{board}/api/health")
    assert health["ok"] is True
    assert health["logdir"] == os.path.abspath(tmp_path)

    snapshot = fetch_json(f"{board}/api/snapshot")
    [run] = snapshot["runs"]
    assert (run["id"], run["status"], run["hparams"]) == ("run", "finished", {"lr": 0.5})
    assert [point[:2] for point in snapshot["scalars"]["run"]["loss"]] == [[0, 0.5]]

    with urlopen(f"{board}/", timeout=5) as response:  # noqa: S310
        assert b"tuff-rl" in response.read()


def test_a_second_script_joins_the_running_board(board, tmp_path):
    assert ensure_board(str(tmp_path), open_browser=False, announce=False) == board


def test_a_stream_from_another_board_is_told_to_reload(board):
    snapshot = fetch_json(f"{board}/api/snapshot")
    with urlopen(f"{board}/api/stream?since={snapshot['seq']}&board=someone-else", timeout=5) as response:  # noqa: S310
        assert response.read(13) == b"event: reset\n"


def test_stop_clears_the_lock(tmp_path):
    url = ensure_board(str(tmp_path), port=free_port(), open_browser=False, announce=False)
    assert url and read_lock(str(tmp_path))
    assert stop_board(str(tmp_path))
    deadline = time.time() + 5
    while read_lock(str(tmp_path)) and time.time() < deadline:
        time.sleep(0.1)
    assert read_lock(str(tmp_path)) is None


def test_binding_does_not_wait_for_reverse_dns(monkeypatch):
    def lookup(*_args):
        raise AssertionError("the board looked up its host name")

    monkeypatch.setattr(socket, "getfqdn", lookup)
    server = _bind("127.0.0.1", free_port(), BoardHandler)
    server.server_close()
