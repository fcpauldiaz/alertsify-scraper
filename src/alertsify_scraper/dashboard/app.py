from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from functools import partial
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from alertsify_scraper import db
from alertsify_scraper.config import Settings
from alertsify_scraper.dashboard.routes import mount_static, router

logger = logging.getLogger(__name__)


def resolve_dashboard_dist() -> Path:
    configured = os.environ.get("DASHBOARD_DIST_DIR", "").strip()
    if configured:
        return Path(configured)

    module_dir = Path(__file__).resolve().parent
    candidates = [
        module_dir / "static",
        Path("/app/dashboard/web/dist"),
        module_dir.parents[3] / "dashboard" / "web" / "dist",
        Path.cwd() / "dashboard" / "web" / "dist",
    ]
    for candidate in candidates:
        if (candidate / "index.html").is_file():
            return candidate
    return candidates[0]


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    await asyncio.to_thread(partial(db.migrate_sync, settings))
    timeout = httpx.Timeout(60.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        app.state.http_client = client
        yield


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or Settings()
    app = FastAPI(title="Alertsify Live Dashboard", lifespan=lifespan)
    app.state.settings = resolved

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[resolved.dashboard_cors_origin.rstrip("/")],
        allow_credentials=True,
        allow_methods=["GET"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.include_router(router)
    dist_dir = resolve_dashboard_dist()
    index = dist_dir / "index.html"
    if index.is_file():
        logger.info("Serving dashboard UI from %s", dist_dir)
    else:
        logger.warning("Dashboard UI dist missing at %s", dist_dir)
    mount_static(app, dist_dir, resolved)
    return app


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings = Settings()
    app = create_app(settings)
    uvicorn.run(
        app,
        host=settings.dashboard_host,
        port=settings.dashboard_port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
