<<<<<<< HEAD
# API-Status-Monitor
Lightweight API uptime &amp; latency monitor with alerts and a simple status dashboard.
=======
# API Status Monitor

Tiny self-hosted dashboard that periodically checks your APIs and shows:

- Current status (UP/DOWN)
- Last check time + latency + HTTP status
- Uptime % (last 24h + all-time)

## Quick start

1) Create your config:

- Copy `config/endpoints.example.json` to `config/endpoints.json`
- Edit URLs (and optional headers/methods/intervals)

2) Run:

```bash
python3 -m app
```

3) Open:

- http://127.0.0.1:8000

## Roadmap ideas (easy weekly upgrades)

- Alerts: email/Discord/Slack webhook when an endpoint changes state
- Charts: sparkline for last 24h latency + availability
- Auth: simple password-protected dashboard
- Tags/groups: group endpoints by product/team
- SLOs: error budget burn, p95 latency, custom success rules

## Config

`config/endpoints.json`:

- `name` (string, unique): Label shown on dashboard
- `url` (string): Full URL to check
- `method` (optional, default `"GET"`): `"GET"`, `"POST"`, `"HEAD"`, ...
- `interval_seconds` (optional, default `30`)
- `timeout_seconds` (optional, default `10`)
- `headers` (optional): JSON object of request headers
- `expected_statuses` (optional): list of HTTP status codes considered “up” (default: any 2xx/3xx)

## API

- `GET /api/status`
- `GET /api/history?name=YourEndpoint&limit=200`

## Data

SQLite DB is stored at `data/monitor.db`.

>>>>>>> 198024d (Initial commit: API Status Monitor)
