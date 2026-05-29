from __future__ import annotations

import asyncio
import logging
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

_DIST = Path(__file__).resolve().parents[3] / "dashboard" / "web" / "dist"


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
    mount_static(app, _DIST)
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
