from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.config import load_endpoints
from app.httpd import serve
from app.monitor import Monitor, MonitorPaths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="API Status Monitor")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--config", default="config/endpoints.json")
    parser.add_argument("--db", default="data/monitor.db")
    parser.add_argument("--web", default="web")
    args = parser.parse_args(argv)

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Config not found: {config_path}", file=sys.stderr)
        print("Tip: copy config/endpoints.example.json to config/endpoints.json", file=sys.stderr)
        return 2

    endpoints = load_endpoints(config_path)
    paths = MonitorPaths(db_path=Path(args.db))
    monitor = Monitor(paths, endpoints)
    monitor.start()

    httpd = serve(
        host=args.host,
        port=int(args.port),
        web_root=Path(args.web),
        db_path=paths.db_path,
        endpoint_ids=monitor.endpoint_ids,
        monitor=monitor,
    )

    try:
        print(f"Listening on http://{args.host}:{args.port}")
        httpd.serve_forever(poll_interval=0.5)
        return 0
    except KeyboardInterrupt:
        return 0
    finally:
        httpd.shutdown()
        httpd.server_close()
        monitor.stop()
