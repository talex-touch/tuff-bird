"""``tuff-bird board <logdir>``, ``tuff-bird stop <logdir>`` and ``tuff-bird plot <logdir> -t <tag>``."""

from __future__ import annotations

import argparse
import re
import webbrowser
from pathlib import Path

from .board.launch import DEFAULT_PORT, can_open_browser, stop_board


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tuff-bird", description="A live board, figures and charts for TensorBoard event files.")
    commands = parser.add_subparsers(dest="command", required=True)

    board = commands.add_parser("board", help="serve the board for a log directory in the foreground")
    board.add_argument("logdir", nargs="?", default="logs")
    board.add_argument("--host", default="127.0.0.1", help="0.0.0.0 to reach it from other machines")
    board.add_argument("--port", type=int, default=DEFAULT_PORT)
    board.add_argument("--no-browser", action="store_true")

    stop = commands.add_parser("stop", help="stop the board serving a log directory")
    stop.add_argument("logdir", nargs="?", default="logs")

    plot = commands.add_parser(
        "plot",
        help="draw tags as a figure for a paper, or as the board's interactive chart",
        description="Draws each tag as a panel. The output's suffix picks the format: .pdf, .svg or .png for a figure "
        "(needs tuff-bird[plot]), .html for the board's interactive chart, which opens offline.",
    )
    plot.add_argument("logdir", nargs="?", default="logs")
    plot.add_argument("-t", "--tag", action="append", required=True, dest="tags", metavar="TAG", help="a scalar tag; repeat it for more panels")
    plot.add_argument("-o", "--output", help="the file to write (default: the tags' names, as .pdf)")
    grouping = plot.add_mutually_exclusive_group()
    grouping.add_argument("--group-by", action="append", metavar="KEY", help="one curve per value of this config key; repeat it to combine keys")
    grouping.add_argument("--no-group", action="store_true", help="one curve per run (default: one per directory of runs, as on the board)")
    plot.add_argument("--smoothing", type=float, default=0.6, help="exponential moving average weight, 0 to 0.999 (default: 0.6)")
    plot.add_argument("--estimator", choices=("mean", "iqm", "median"), default="mean", help="the line across a curve's runs (default: mean)")
    plot.add_argument("--band", choices=("ci", "std", "se", "minmax", "none"), default="ci", help="the band around it (default: ci, a 95%% bootstrap interval)")
    plot.add_argument("--no-truncate", action="store_true", help="keep the steps past where the shortest run stops")
    plot.add_argument("--raw", action="store_true", help="also draw the values as logged, faintly")
    plot.add_argument("--title")

    args = parser.parse_args(argv)
    if args.command == "plot":
        return _plot(args, plot)
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


def _plot(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from .experiment import BY_DIRECTORY, load

    output = Path(args.output or "_".join(re.sub(r"[^\w.-]+", "-", tag).strip("-") or "chart" for tag in args.tags) + ".pdf")
    group_by = None if args.no_group else args.group_by or BY_DIRECTORY
    try:
        experiment = load(args.logdir)
        if output.suffix.lower() in (".html", ".htm"):
            ignored = [f"--{name.replace('_', '-')}" for name in ("estimator", "band", "no_truncate", "raw") if getattr(args, name) != parser.get_default(name)]
            if ignored:
                print(f"[tuffbird] {', '.join(ignored)}: figures only; the chart draws each group as the board does, the mean ± one standard deviation")
            experiment.chart(args.tags, group_by=group_by, smoothing=args.smoothing, title=args.title).save(output)
            print(f"[tuffbird] wrote {output}")
            return 0
        figure = experiment.plot(
            args.tags, group_by=group_by, smoothing=args.smoothing, estimator=args.estimator, band=args.band,
            truncate=not args.no_truncate, raw=args.raw, title=args.title,
        )
        figure.savefig(output)
    except (FileNotFoundError, ImportError, ValueError) as error:
        print(f"[tuffbird] {error}")
        return 1
    print(f"[tuffbird] wrote {output}")
    print(f"Caption: {figure.tuffbird_caption}")
    return 0
