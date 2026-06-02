from __future__ import annotations

import asyncio
import logging
from functools import partial
from pathlib import Path
from typing import Annotated, Any, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from alertsify_scraper import db
from alertsify_scraper.dashboard.serializers import (
    equity_point_to_dict,
    summary_to_dict,
    trade_to_dict,
)
from alertsify_scraper.dashboard.service import DashboardService
from alertsify_scraper.performance import PeriodFilter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


def get_service(request: Request) -> DashboardService:
    return DashboardService(request.app.state.settings)


def get_http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http_client


PeriodQuery = Annotated[
    Literal["all", "7d", "30d"],
    Query(alias="period"),
]


def _libsql_storage_kind(url: str) -> str:
    if url.startswith("file:"):
        return "file"
    if url.startswith("libsql:"):
        return "remote"
    return "other"


@router.get("/health")
async def health(
    request: Request,
    service: DashboardService = Depends(get_service),
) -> dict[str, Any]:
    settings = request.app.state.settings
    counts, summary = await asyncio.gather(
        asyncio.to_thread(partial(db.trade_counts_by_mode_sync, settings)),
        asyncio.to_thread(partial(db.live_trade_summary_sync, settings)),
    )
    live_in_db = counts.get("live", 0)
    paper_in_db = counts.get("paper", 0)
    return {
        "status": "ok",
        "service": "alertsify-dashboard",
        "live_tradier_configured": service.live_configured(),
        "libsql_storage": _libsql_storage_kind(settings.libsql_url),
        "placed_trades_live": live_in_db,
        "placed_trades_paper": paper_in_db,
        "open_live_trades": summary.open_count,
        "scraper_note": (
            "Scraper writes placed_trades; this API reads only trading_mode=live. "
            "Docker default CMD runs both via alertsify-run-all."
        ),
        "process_checks": [
            "Use alertsify-run-all (image default) or keep scraper + dashboard on one LIBSQL_URL.",
            "With file: URLs in Docker, use file:/var/lib/alertsify/db.sqlite and a volume.",
            "Configure ALERTSIFY_USER_ID_LIVE for rows the dashboard can show.",
        ],
    }


@router.get("/live/summary")
async def live_summary(
    period: PeriodQuery = "all",
    service: DashboardService = Depends(get_service),
    client: httpx.AsyncClient = Depends(get_http_client),
) -> dict:
    if not service.live_configured():
        raise HTTPException(
            status_code=503,
            detail="Tradier live credentials are not configured",
        )
    try:
        summary = await service.get_summary(client, period=period)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Tradier request failed: {exc}") from exc
    return {"period": period, **summary_to_dict(summary)}


@router.get("/live/trades")
async def live_trades(
    period: PeriodQuery = "all",
    status: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 500,
    service: DashboardService = Depends(get_service),
    client: httpx.AsyncClient = Depends(get_http_client),
) -> dict:
    if status is not None and status not in ("open", "closed"):
        raise HTTPException(status_code=400, detail="status must be open or closed")
    if not service.live_configured():
        raise HTTPException(
            status_code=503,
            detail="Tradier live credentials are not configured",
        )
    try:
        trades = await service.get_trades(
            client,
            period=period,
            status=status,
            limit=limit,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Tradier request failed: {exc}") from exc
    return {
        "period": period,
        "count": len(trades),
        "trades": [trade_to_dict(t) for t in trades],
    }


@router.get("/live/equity-curve")
async def live_equity_curve(
    period: PeriodQuery = "all",
    service: DashboardService = Depends(get_service),
    client: httpx.AsyncClient = Depends(get_http_client),
) -> dict:
    if not service.live_configured():
        raise HTTPException(
            status_code=503,
            detail="Tradier live credentials are not configured",
        )
    try:
        points = await service.get_equity_curve(client, period=period)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Tradier request failed: {exc}") from exc
    return {
        "period": period,
        "points": [equity_point_to_dict(p) for p in points],
    }


def mount_static(app, dist_dir: Path) -> None:
    index = dist_dir / "index.html"
    if not dist_dir.is_dir() or not index.is_file():
        @app.get("/")
        async def root_without_ui() -> dict[str, str]:
            logger.warning("Dashboard UI dist missing at %s", dist_dir)
            return {
                "status": "api_only",
                "message": "Dashboard UI is not built. Use /api/health and /api/live/*.",
            }

        return

    index_html = index.read_text(encoding="utf-8")

    app.mount("/assets", StaticFiles(directory=dist_dir / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str) -> HTMLResponse:
        if full_path.startswith("api"):
            raise HTTPException(status_code=404)
        return HTMLResponse(index_html)
