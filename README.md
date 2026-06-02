# alertsify-scraper

Polls Alertsify option positions and mirrors new legs to Tradier (paper or live), with Turso dedupe and ntfy alerts.

## Live trade performance dashboard

A separate web UI shows **live trading only** (paper trades are excluded). It reads `placed_trades` from libSQL/Turso and enriches open/closed P&L from the Tradier live account.

### Setup

1. Copy `.env.example` to `.env` and configure `TRADIER_LIVE_*`, `LIBSQL_*`, and Alertsify settings as for the scraper.
2. Install Python dependencies: `pip install -e ".[dev]"`
3. Install dashboard UI: `cd dashboard/web && npm install`

### Run (development)

Both processes (matches Docker):

```bash
alertsify-run-all
```

Or split terminals — API:

```bash
alertsify-dashboard
```

UI with hot reload:

```bash
cd dashboard/web && npm run dev
```

Open http://127.0.0.1:5173.

### Run (production static)

```bash
cd dashboard/web && npm run build
alertsify-run-all
```

Built assets are served from `dashboard/web/dist` at the same host as the API (default http://127.0.0.1:8080).

### Scraper ↔ dashboard process contract

The two processes **do not talk over HTTP**. They only share **libSQL/Turso** (`placed_trades`):

| Scraper | Dashboard |
| ------- | --------- |
| Polls Alertsify, places on Tradier | Reads `placed_trades` where `trading_mode = 'live'` |
| `INSERT` with each user’s mode (`paper` or `live`) | Enriches those rows from **live** Tradier only |

Common “scraper works, dashboard empty” cases:

1. **Wrong file DB path in Docker** — use Turso (`libsql://...`) or `file:/var/lib/alertsify/db.sqlite` with the compose volume (not `file:./local.db` inside the container).
2. **Paper-only scraper** — trades are stored as `trading_mode=paper`; the UI only shows **live** rows. Add users under `ALERTSIFY_USER_ID_LIVE`.
3. **Dashboard-only override** — if you start `alertsify-dashboard` alone, polling does not run.

Check coupling: `GET /api/health` returns `placed_trades_live`, `placed_trades_paper`, and `libsql_storage` (`file` vs `remote`).

### Run (Docker / Coolify)

**Default (one container):** `alertsify-run-all` runs the scraper subprocess and dashboard on port **8080**. Same process shares one `LIBSQL_URL` (no split-database issue).

| Command | When to use |
| ------- | ----------- |
| `alertsify-run-all` (Dockerfile default) | Production / Coolify — scraper + UI |
| `alertsify-dashboard` | UI/API only |
| `alertsify-scraper` | Polling only |

Local:

```bash
docker compose up --build
```

Or:

```bash
docker build -t alertsify-scraper .
docker run --rm -p 8080:8080 --env-file .env alertsify-scraper
```

Coolify: deploy the image with port **8080** and leave the start command empty (uses `alertsify-run-all`). Set env vars as in `.env.example`.

Split into two containers (optional): `docker compose --profile split up`.

Verify: logs include `Poll cycle finished` (market hours) and `GET /api/live/*`; `GET /api/health` shows `placed_trades_live` / `placed_trades_paper`.

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
