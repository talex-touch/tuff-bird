"""``tuff-bird board <logdir>`` and ``tuff-bird stop <logdir>``."""

from __future__ import annotations

import argparse
import webbrowser

from .board.launch import DEFAULT_PORT, can_open_browser, stop_board


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tuff-bird", description="Live board for TensorBoard event files.")
    commands = parser.add_subparsers(dest="command", required=True)

    board = commands.add_parser("board", help="serve the board for a log directory in the foreground")
    board.add_argument("logdir", nargs="?", default="logs")
    board.add_argument("--host", default="127.0.0.1", help="0.0.0.0 to reach it from other machines")
    board.add_argument("--port", type=int, default=DEFAULT_PORT)
    board.add_argument("--no-browser", action="store_true")

    stop = commands.add_parser("stop", help="stop the board serving a log directory")
    stop.add_argument("logdir", nargs="?", default="logs")

    args = parser.parse_args(argv)
    if args.command == "stop":
        stopped = stop_board(args.logdir)
        print("[tuffbird] stopped" if stopped else "[tuffbird] no board is serving that directory")
        return 0 if stopped else 1

    from .board.server import serve

    if not args.no_browser and can_open_browser():
        # Open once the server is listening; serve() prints the URL it bound.
        import threading

        from .board.lock import read_lock

        def open_when_ready() -> None:
            import time

            for _ in range(50):
                info = read_lock(args.logdir)
                if info and info.get("url"):
                    webbrowser.open(info["url"])
                    return
                time.sleep(0.1)

        threading.Thread(target=open_when_ready, daemon=True).start()
    serve(args.logdir, host=args.host, port=args.port)
    return 0
