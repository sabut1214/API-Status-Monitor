from __future__ import annotations

import json
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from app.db import connect, get_history, get_last_check, get_uptime
from app.monitor import Monitor


def _json(handler: BaseHTTPRequestHandler, status: int, payload: Any) -> None:
    data = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _text(handler: BaseHTTPRequestHandler, status: int, text: str, content_type: str) -> None:
    data = text.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _read_file(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


class Handler(BaseHTTPRequestHandler):
    server_version = "api-status-monitor/1.0"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._serve_file(self.server.web_root / "index.html", "text/html; charset=utf-8")
            return
        if parsed.path.startswith("/static/"):
            rel = parsed.path.removeprefix("/static/")
            self._serve_static(rel)
            return
        if parsed.path == "/api/status":
            self._handle_status()
            return
        if parsed.path == "/api/history":
            self._handle_history(parsed.query)
            return
        _text(self, HTTPStatus.NOT_FOUND, "Not Found", "text/plain; charset=utf-8")

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/check-now":
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw = self.rfile.read(length) if length else b"{}"
            try:
                body = json.loads(raw.decode("utf-8") or "{}")
            except Exception:  # noqa: BLE001
                _json(self, HTTPStatus.BAD_REQUEST, {"error": "Invalid JSON body"})
                return
            name = body.get("name")
            if not isinstance(name, str) or not name.strip():
                _json(self, HTTPStatus.BAD_REQUEST, {"error": "Missing 'name'"})
                return
            ok = self.server.monitor.check_now(name.strip())
            if not ok:
                _json(self, HTTPStatus.NOT_FOUND, {"error": "Unknown endpoint"})
                return
            _json(self, HTTPStatus.ACCEPTED, {"ok": True})
            return
        _text(self, HTTPStatus.NOT_FOUND, "Not Found", "text/plain; charset=utf-8")

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        # Keep default logging but slightly quieter for polling endpoints.
        super().log_message(fmt, *args)

    def _serve_file(self, path: Path, content_type: str) -> None:
        data = _read_file(path)
        if data is None:
            _text(self, HTTPStatus.NOT_FOUND, "Not Found", "text/plain; charset=utf-8")
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_static(self, rel: str) -> None:
        path = (self.server.web_root / "static" / rel).resolve()
        # Prevent directory traversal
        if self.server.web_root.resolve() not in path.parents:
            _text(self, HTTPStatus.FORBIDDEN, "Forbidden", "text/plain; charset=utf-8")
            return
        ext = path.suffix.lower()
        if ext == ".css":
            ctype = "text/css; charset=utf-8"
        elif ext == ".js":
            ctype = "text/javascript; charset=utf-8"
        elif ext == ".svg":
            ctype = "image/svg+xml"
        else:
            ctype = "application/octet-stream"
        self._serve_file(path, ctype)

    def _handle_status(self) -> None:
        conn = connect(self.server.db_path)
        now = int(time.time())
        since_24h = now - 24 * 60 * 60
        try:
            out = []
            for name, endpoint_id in self.server.endpoint_ids.items():
                last = get_last_check(conn, endpoint_id)
                up24, total24 = get_uptime(conn, endpoint_id, since_24h)
                upall, totalall = get_uptime(conn, endpoint_id, None)

                def pct(up: int, total: int) -> float | None:
                    if total == 0:
                        return None
                    return round((up / total) * 100.0, 2)

                out.append(
                    {
                        "name": name,
                        "last": None
                        if last is None
                        else {
                            "checked_at": last.checked_at,
                            "ok": last.ok,
                            "status_code": last.status_code,
                            "latency_ms": last.latency_ms,
                            "error": last.error,
                        },
                        "uptime_24h": {"up": up24, "total": total24, "pct": pct(up24, total24)},
                        "uptime_all": {"up": upall, "total": totalall, "pct": pct(upall, totalall)},
                    }
                )
            out.sort(key=lambda x: x["name"].lower())
            _json(self, HTTPStatus.OK, {"endpoints": out, "now": now})
        finally:
            conn.close()

    def _handle_history(self, query: str) -> None:
        qs = parse_qs(query)
        name = (qs.get("name") or [None])[0]
        limit_raw = (qs.get("limit") or [None])[0]
        if not isinstance(name, str) or not name.strip():
            _json(self, HTTPStatus.BAD_REQUEST, {"error": "Missing 'name' query param"})
            return
        limit = 200
        if isinstance(limit_raw, str) and limit_raw.strip():
            try:
                limit = max(1, min(2000, int(limit_raw)))
            except ValueError:
                _json(self, HTTPStatus.BAD_REQUEST, {"error": "Invalid 'limit'"})
                return
        endpoint_id = self.server.endpoint_ids.get(name.strip())
        if endpoint_id is None:
            _json(self, HTTPStatus.NOT_FOUND, {"error": "Unknown endpoint"})
            return
        conn = connect(self.server.db_path)
        try:
            rows = get_history(conn, endpoint_id, limit)
            _json(
                self,
                HTTPStatus.OK,
                {
                    "name": name.strip(),
                    "history": [
                        {
                            "checked_at": r.checked_at,
                            "ok": r.ok,
                            "status_code": r.status_code,
                            "latency_ms": r.latency_ms,
                            "error": r.error,
                        }
                        for r in rows
                    ],
                },
            )
        finally:
            conn.close()


class StatusHTTPServer(ThreadingHTTPServer):
    def __init__(self, addr: tuple[str, int], handler: type[BaseHTTPRequestHandler]) -> None:
        super().__init__(addr, handler)
        self.web_root: Path
        self.db_path: Path
        self.endpoint_ids: dict[str, int]
        self.monitor: Monitor


def serve(
    *,
    host: str,
    port: int,
    web_root: Path,
    db_path: Path,
    endpoint_ids: dict[str, int],
    monitor: Monitor,
) -> StatusHTTPServer:
    httpd = StatusHTTPServer((host, port), Handler)
    httpd.web_root = web_root
    httpd.db_path = db_path
    httpd.endpoint_ids = endpoint_ids
    httpd.monitor = monitor
    return httpd

