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

The image supports **two commands** (same env, especially `LIBSQL_URL`):

| Command | Role | Logs to expect |
| ------- | ---- | -------------- |
| `alertsify-dashboard` (Dockerfile default) | API + UI on port 8080 | `uvicorn`, `GET /api/live/*` |
| `alertsify-scraper` | Poll Alertsify → Tradier → Turso | `Poll cycle started`, `Poll cycle finished ... placed=N` |

**The dashboard does not poll Alertsify.** If you only deploy the default container, you will never see `Poll cycle finished` and no new trades are written to the database.

Local (both processes):

```bash
docker compose up --build
```

Or manually:

```bash
docker build -t alertsify-scraper .
docker run --rm -p 8080:8080 --env-file .env alertsify-scraper alertsify-dashboard
docker run --rm --env-file .env alertsify-scraper alertsify-scraper
```

In Coolify:

1. **Dashboard app** — expose port **8080**, start command `alertsify-dashboard` (or empty for image default).
2. **Scraper app** (second service, same image + env) — start command `alertsify-scraper`, no public port; tail logs during market hours.
3. Both must use the **same** `LIBSQL_URL` / Turso credentials.
4. Verify dashboard: `GET /api/health` → `"service": "alertsify-dashboard"`.
5. Verify scraper: logs show `Alertsify users: N total` then, between 09:30–16:00 US/Eastern, `Poll cycle finished`.

Outside market hours (`POLL_MARKET_HOURS_ONLY=true`), the scraper logs `Outside market session ... sleeping` instead of poll cycles.

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
