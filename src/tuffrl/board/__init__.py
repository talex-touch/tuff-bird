"""The live board: a local web page that follows the event files in a log directory."""

from .launch import ensure_board, stop_board

__all__ = ["ensure_board", "stop_board"]
