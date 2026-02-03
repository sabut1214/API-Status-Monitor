from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class EndpointConfig:
    name: str
    url: str
    method: str = "GET"
    interval_seconds: int = 30
    timeout_seconds: int = 10
    headers: dict[str, str] | None = None
    expected_statuses: list[int] | None = None


def _validate_endpoint(raw: dict[str, Any]) -> EndpointConfig:
    if not isinstance(raw.get("name"), str) or not raw["name"].strip():
        raise ValueError("Endpoint is missing non-empty 'name'")
    if not isinstance(raw.get("url"), str) or not raw["url"].strip():
        raise ValueError(f"Endpoint '{raw.get('name', '')}' is missing non-empty 'url'")

    method = raw.get("method", "GET")
    if not isinstance(method, str) or not method.strip():
        raise ValueError(f"Endpoint '{raw['name']}' has invalid 'method'")

    interval = raw.get("interval_seconds", 30)
    timeout = raw.get("timeout_seconds", 10)
    if not isinstance(interval, int) or interval < 5:
        raise ValueError(f"Endpoint '{raw['name']}' has invalid 'interval_seconds' (min 5)")
    if not isinstance(timeout, int) or timeout < 1:
        raise ValueError(f"Endpoint '{raw['name']}' has invalid 'timeout_seconds' (min 1)")

    headers = raw.get("headers")
    if headers is not None:
        if not isinstance(headers, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in headers.items()):
            raise ValueError(f"Endpoint '{raw['name']}' has invalid 'headers' (must be string->string)")

    expected_statuses = raw.get("expected_statuses")
    if expected_statuses is not None:
        if not isinstance(expected_statuses, list) or not all(isinstance(x, int) for x in expected_statuses):
            raise ValueError(f"Endpoint '{raw['name']}' has invalid 'expected_statuses' (must be list[int])")

    return EndpointConfig(
        name=raw["name"].strip(),
        url=raw["url"].strip(),
        method=method.strip().upper(),
        interval_seconds=interval,
        timeout_seconds=timeout,
        headers=headers,
        expected_statuses=expected_statuses,
    )


def load_endpoints(config_path: Path) -> list[EndpointConfig]:
    data = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Config file must contain a JSON list of endpoints")
    endpoints = [_validate_endpoint(x) for x in data]
    names = [e.name for e in endpoints]
    if len(set(names)) != len(names):
        raise ValueError("Endpoint names must be unique")
    return endpoints

