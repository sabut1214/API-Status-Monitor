from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from app.config import EndpointConfig
from app.db import connect, insert_check, upsert_endpoint


@dataclass(frozen=True)
class MonitorPaths:
    db_path: Path


def _is_ok_status(status: int, expected_statuses: list[int] | None) -> bool:
    if expected_statuses:
        return status in expected_statuses
    return 200 <= status < 400


def run_check(endpoint: EndpointConfig) -> tuple[bool, int | None, int | None, str | None]:
    req = urllib.request.Request(
        endpoint.url,
        method=endpoint.method,
        headers=endpoint.headers or {},
    )

    start = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=endpoint.timeout_seconds) as resp:
            status = getattr(resp, "status", None)
            if status is None:
                status = resp.getcode()
            latency_ms = int((time.monotonic() - start) * 1000)
            ok = _is_ok_status(int(status), endpoint.expected_statuses)
            return ok, int(status), latency_ms, None
    except urllib.error.HTTPError as e:
        latency_ms = int((time.monotonic() - start) * 1000)
        status = int(getattr(e, "code", 0) or 0) or None
        ok = False
        return ok, status, latency_ms, str(e)
    except Exception as e:  # noqa: BLE001
        latency_ms = int((time.monotonic() - start) * 1000)
        return False, None, latency_ms, f"{type(e).__name__}: {e}"


class Monitor:
    def __init__(self, paths: MonitorPaths, endpoints: list[EndpointConfig]) -> None:
        self._paths = paths
        self._endpoints = endpoints
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

        self._endpoint_ids: dict[str, int] = {}

    @property
    def endpoint_ids(self) -> dict[str, int]:
        # Treat as read-only after start(); used by HTTP layer for lookups.
        return self._endpoint_ids

    def start(self) -> None:
        conn = connect(self._paths.db_path)
        try:
            for ep in self._endpoints:
                endpoint_id = upsert_endpoint(
                    conn,
                    name=ep.name,
                    url=ep.url,
                    method=ep.method,
                    interval_seconds=ep.interval_seconds,
                    timeout_seconds=ep.timeout_seconds,
                    headers_json=json.dumps(ep.headers) if ep.headers else None,
                    expected_statuses_json=json.dumps(ep.expected_statuses) if ep.expected_statuses else None,
                )
                self._endpoint_ids[ep.name] = endpoint_id
        finally:
            conn.close()

        for ep in self._endpoints:
            t = threading.Thread(target=self._loop_endpoint, name=f"monitor:{ep.name}", args=(ep,), daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self) -> None:
        self._stop.set()
        for t in self._threads:
            t.join(timeout=2)

    def check_now(self, name: str) -> bool:
        ep = next((e for e in self._endpoints if e.name == name), None)
        if ep is None:
            return False
        threading.Thread(target=self._check_and_store, name=f"check-now:{name}", args=(ep,), daemon=True).start()
        return True

    def _loop_endpoint(self, ep: EndpointConfig) -> None:
        # Stagger initial check slightly to avoid all endpoints firing at once.
        time.sleep(0.2)
        while not self._stop.is_set():
            self._check_and_store(ep)
            self._stop.wait(ep.interval_seconds)

    def _check_and_store(self, ep: EndpointConfig) -> None:
        ok, status, latency_ms, error = run_check(ep)
        checked_at = int(time.time())
        conn = connect(self._paths.db_path)
        try:
            endpoint_id = self._endpoint_ids[ep.name]
            insert_check(
                conn,
                endpoint_id=endpoint_id,
                checked_at=checked_at,
                ok=ok,
                status_code=status,
                latency_ms=latency_ms,
                error=error,
            )
        finally:
            conn.close()
