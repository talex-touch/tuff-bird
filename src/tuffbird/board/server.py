"""The board's HTTP server: the built web page, a snapshot, and a stream of what changed since."""

from __future__ import annotations

import json
import mimetypes
import os
import signal
import socket
import socketserver
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from .. import __version__
from .lock import clear_lock, write_lock
from .store import Store

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
POLL_SECS = 0.5
KEEPALIVE_SECS = 15.0

_MISSING_PAGE = b"""<!doctype html><meta charset="utf-8"><title>tuff-bird</title>
<p>The board page has not been built. Run <code>pnpm install &amp;&amp; pnpm build</code> in
<code>web/</code>; the API is up at <a href="/api/snapshot">/api/snapshot</a>.</p>"""


def _json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, separators=(",", ":"), allow_nan=False, default=str).encode("utf-8")


def _sanitize(payload: Any) -> Any:
    """JSON has no NaN or infinity; they travel as strings the page turns back into numbers."""
    if isinstance(payload, float):
        if payload != payload:
            return "NaN"
        if payload in (float("inf"), float("-inf")):
            return "Infinity" if payload > 0 else "-Infinity"
        return payload
    if isinstance(payload, list):
        return [_sanitize(item) for item in payload]
    if isinstance(payload, dict):
        return {key: _sanitize(value) for key, value in payload.items()}
    return payload


class BoardHandler(BaseHTTPRequestHandler):
    server_version = f"tuff-bird/{__version__}"
    store: Store  # set on the subclass made per server

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - signature from the base class
        pass  # a busy page would otherwise flood the board's log

    def _send(self, status: int, body: bytes, content_type: str, *, cache: str = "no-store") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - name from the base class
        url = urlparse(self.path)
        if url.path == "/api/health":
            self._send(HTTPStatus.OK, _json_bytes({"ok": True, "logdir": self.store.logdir, "pid": os.getpid(), "version": __version__}), "application/json")
        elif url.path == "/api/snapshot":
            self._send(HTTPStatus.OK, _json_bytes(_sanitize(self.store.snapshot())), "application/json")
        elif url.path == "/api/stream":
            query = parse_qs(url.query)
            since = int((query.get("since") or ["0"])[0] or 0)
            board = (query.get("board") or [""])[0]
            self._stream(since, resumable=board in ("", self.store.instance))
        else:
            self._static(url.path)

    def _static(self, path: str) -> None:
        relative = os.path.normpath(path.lstrip("/")) if path not in ("", "/") else "index.html"
        if relative.startswith(".."):
            self._send(HTTPStatus.NOT_FOUND, b"not found", "text/plain")
            return
        file_path = os.path.join(STATIC_DIR, relative)
        if not os.path.isfile(file_path):
            file_path = os.path.join(STATIC_DIR, "index.html")  # the page routes itself
        if not os.path.isfile(file_path):
            self._send(HTTPStatus.OK, _MISSING_PAGE, "text/html; charset=utf-8")
            return
        with open(file_path, "rb") as handle:
            body = handle.read()
        content_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in ("application/javascript", "image/svg+xml"):
            content_type += "; charset=utf-8"
        hashed = "/assets/" in path
        self._send(HTTPStatus.OK, body, content_type, cache="public, max-age=31536000, immutable" if hashed else "no-cache")

    def _stream(self, since: int, *, resumable: bool) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        last_sent = time.monotonic()
        try:
            while True:
                deltas = self.store.wait_deltas(since, timeout=KEEPALIVE_SECS) if resumable else None
                if deltas is None:
                    self.wfile.write(b"event: reset\ndata: {}\n\n")
                    self.wfile.flush()
                    return
                if deltas:
                    chunks = []
                    for delta in deltas:
                        chunks.append(b"id: %d\ndata: " % delta["seq"] + _json_bytes(_sanitize(delta)) + b"\n\n")
                    since = deltas[-1]["seq"]
                    self.wfile.write(b"".join(chunks))
                    self.wfile.flush()
                    last_sent = time.monotonic()
                elif time.monotonic() - last_sent >= KEEPALIVE_SECS:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    last_sent = time.monotonic()
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            return


class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def server_bind(self) -> None:
        # HTTPServer.server_bind() looks up the host's fully qualified name, which blocks for
        # many seconds where reverse DNS is slow (GitHub's macOS runners, some offline
        # machines). Nothing here uses that name.
        socketserver.TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name = str(host)
        self.server_port = port


def _bind(host: str, port: int, handler: type[BaseHTTPRequestHandler], tries: int = 20) -> ThreadingHTTPServer:
    last_error: OSError | None = None
    for candidate in range(port, port + tries):
        try:
            return _Server((host, candidate), handler)
        except OSError as error:  # port taken
            last_error = error
    raise OSError(f"no free port in {port}..{port + tries - 1}") from last_error


def serve(logdir: str, *, host: str = "127.0.0.1", port: int = 6066, announce: bool = True) -> None:
    store = Store(logdir)
    store.scan()
    handler = type("Handler", (BoardHandler,), {"store": store})
    server = _bind(host, port, handler)
    bound_port = server.server_address[1]
    url_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    url = f"http://{url_host}:{bound_port}"
    write_lock(store.logdir, {"pid": os.getpid(), "host": host, "port": bound_port, "url": url,
                              "logdir": store.logdir, "machine": socket.gethostname(), "startedAt": time.time()})

    stop = threading.Event()

    def watch() -> None:
        while not stop.wait(POLL_SECS):
            try:
                store.scan()
            except Exception as error:  # noqa: BLE001 - a bad file must not stop the board
                print(f"[tuffbird] scan failed: {error}", file=sys.stderr)

    watcher = threading.Thread(target=watch, name="tuffbird-watch", daemon=True)
    watcher.start()

    def shutdown(*_args: Any) -> None:
        stop.set()
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, shutdown)
    if announce:
        print(f"[tuffbird] board for {store.logdir}: {url}", flush=True)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()
        clear_lock(store.logdir, os.getpid())
