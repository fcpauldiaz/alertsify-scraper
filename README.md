# alertsify-scraper

Polls Alertsify option positions and mirrors new legs to Tradier (paper or live), with Turso dedupe and ntfy alerts.

## Live trade performance dashboard

A separate web UI shows **live trading only** (paper trades are excluded). It reads `placed_trades` from libSQL/Turso and enriches open/closed P&L from the Tradier live account.

### Setup

1. Copy `.env.example` to `.env` and configure `TRADIER_LIVE_*`, `LIBSQL_*`, and Alertsify settings as for the scraper.
2. Install Python dependencies: `pip install -e ".[dev]"`
3. Install dashboard UI: `cd dashboard/web && npm install`

### Run (development)

Terminal 1 — API:

```bash
alertsify-dashboard
```

Terminal 2 — UI with hot reload:

```bash
cd dashboard/web && npm run dev
```

Open http://127.0.0.1:5173.

### Run (production static)

```bash
cd dashboard/web && npm run build
alertsify-dashboard
```

Built assets are served from `dashboard/web/dist` at the same host as the API (default http://127.0.0.1:8080).

### Run (Docker / Coolify)

The Dockerfile builds the React UI and starts `alertsify-dashboard` on port **8080** with `DASHBOARD_HOST=0.0.0.0`.

```bash
docker build -t alertsify-dashboard .
docker run --rm -p 8080:8080 --env-file .env alertsify-dashboard
```

In Coolify:

1. Expose container port **8080** (matches `DASHBOARD_PORT`).
2. Leave **Start Command** empty so the image runs `alertsify-dashboard`.
3. Set `DASHBOARD_HOST=0.0.0.0` (already the Docker default).
4. Verify: `GET /api/health` returns JSON before opening `/`.

If `/` returns 404 but `/api/health` works, rebuild the image — the UI was not included in the deploy.

### API

| Endpoint | Description |
| -------- | ----------- |
| `GET /api/health` | Liveness and whether live Tradier is configured |
| `GET /api/live/summary?period=all\|7d\|30d` | Portfolio KPIs |
| `GET /api/live/trades?period=...` | Trade list with P&L |
| `GET /api/live/equity-curve?period=...` | Cumulative realized P&L by day |

### Design

UI follows the project [`.impeccable.md`](.impeccable.md) product register (IBM Plex, OKLCH neutrals, dense tables). Install [Impeccable](https://impeccable.style) skills locally with `npx impeccable skills install` for design audits.

### Tests

```bash
pytest
```
