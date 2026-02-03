from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path


SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS endpoints (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  url TEXT NOT NULL,
  method TEXT NOT NULL,
  interval_seconds INTEGER NOT NULL,
  timeout_seconds INTEGER NOT NULL,
  headers_json TEXT,
  expected_statuses_json TEXT,
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS checks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  endpoint_id INTEGER NOT NULL,
  checked_at INTEGER NOT NULL,
  ok INTEGER NOT NULL,
  status_code INTEGER,
  latency_ms INTEGER,
  error TEXT,
  FOREIGN KEY(endpoint_id) REFERENCES endpoints(id)
);

CREATE INDEX IF NOT EXISTS idx_checks_endpoint_time ON checks(endpoint_id, checked_at);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=10, isolation_level=None)
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.executescript(SCHEMA_SQL)
    return conn


def upsert_endpoint(
    conn: sqlite3.Connection,
    *,
    name: str,
    url: str,
    method: str,
    interval_seconds: int,
    timeout_seconds: int,
    headers_json: str | None,
    expected_statuses_json: str | None,
) -> int:
    now = int(time.time())
    conn.execute(
        """
        INSERT INTO endpoints (name, url, method, interval_seconds, timeout_seconds, headers_json, expected_statuses_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
          url=excluded.url,
          method=excluded.method,
          interval_seconds=excluded.interval_seconds,
          timeout_seconds=excluded.timeout_seconds,
          headers_json=excluded.headers_json,
          expected_statuses_json=excluded.expected_statuses_json
        """,
        (name, url, method, interval_seconds, timeout_seconds, headers_json, expected_statuses_json, now),
    )
    row = conn.execute("SELECT id FROM endpoints WHERE name = ?", (name,)).fetchone()
    assert row is not None
    return int(row[0])


@dataclass(frozen=True)
class CheckRow:
    checked_at: int
    ok: bool
    status_code: int | None
    latency_ms: int | None
    error: str | None


def insert_check(
    conn: sqlite3.Connection,
    *,
    endpoint_id: int,
    checked_at: int,
    ok: bool,
    status_code: int | None,
    latency_ms: int | None,
    error: str | None,
) -> None:
    conn.execute(
        """
        INSERT INTO checks (endpoint_id, checked_at, ok, status_code, latency_ms, error)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (endpoint_id, checked_at, 1 if ok else 0, status_code, latency_ms, error),
    )


def get_last_check(conn: sqlite3.Connection, endpoint_id: int) -> CheckRow | None:
    row = conn.execute(
        """
        SELECT checked_at, ok, status_code, latency_ms, error
        FROM checks
        WHERE endpoint_id = ?
        ORDER BY checked_at DESC, id DESC
        LIMIT 1
        """,
        (endpoint_id,),
    ).fetchone()
    if row is None:
        return None
    return CheckRow(
        checked_at=int(row[0]),
        ok=bool(row[1]),
        status_code=row[2] if row[2] is None else int(row[2]),
        latency_ms=row[3] if row[3] is None else int(row[3]),
        error=row[4],
    )


def get_uptime(conn: sqlite3.Connection, endpoint_id: int, since_ts: int | None) -> tuple[int, int]:
    if since_ts is None:
        row = conn.execute(
            "SELECT SUM(ok), COUNT(*) FROM checks WHERE endpoint_id = ?",
            (endpoint_id,),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT SUM(ok), COUNT(*) FROM checks WHERE endpoint_id = ? AND checked_at >= ?",
            (endpoint_id, since_ts),
        ).fetchone()
    up = int(row[0] or 0)
    total = int(row[1] or 0)
    return up, total


def get_history(conn: sqlite3.Connection, endpoint_id: int, limit: int) -> list[CheckRow]:
    rows = conn.execute(
        """
        SELECT checked_at, ok, status_code, latency_ms, error
        FROM checks
        WHERE endpoint_id = ?
        ORDER BY checked_at DESC, id DESC
        LIMIT ?
        """,
        (endpoint_id, limit),
    ).fetchall()
    return [
        CheckRow(
            checked_at=int(r[0]),
            ok=bool(r[1]),
            status_code=r[2] if r[2] is None else int(r[2]),
            latency_ms=r[3] if r[3] is None else int(r[3]),
            error=r[4],
        )
        for r in rows
    ]

