from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from alertsify_scraper.config import Settings
from alertsify_scraper.dashboard.auth import require_dashboard_auth
from alertsify_scraper.dashboard.serializers import (
    equity_point_to_dict,
    summary_to_dict,
    trade_to_dict,
)
from alertsify_scraper.dashboard.service import DashboardService
from alertsify_scraper.performance import PeriodFilter

router = APIRouter(prefix="/api")


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_service(settings: Settings = Depends(get_settings)) -> DashboardService:
    return DashboardService(settings)


def get_http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http_client


PeriodQuery = Annotated[
    Literal["all", "7d", "30d"],
    Query(alias="period"),
]


@router.get("/health")
async def health(
    service: DashboardService = Depends(get_service),
) -> dict[str, bool | str]:
    return {
        "status": "ok",
        "live_tradier_configured": service.live_configured(),
    }


@router.get("/live/summary", dependencies=[Depends(require_dashboard_auth)])
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


@router.get("/live/trades", dependencies=[Depends(require_dashboard_auth)])
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


@router.get("/live/equity-curve", dependencies=[Depends(require_dashboard_auth)])
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
    if not dist_dir.is_dir():
        return
    app.mount("/assets", StaticFiles(directory=dist_dir / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str) -> FileResponse:
        if full_path.startswith("api"):
            raise HTTPException(status_code=404)
        index = dist_dir / "index.html"
        if not index.is_file():
            raise HTTPException(status_code=404)
        return FileResponse(index)
