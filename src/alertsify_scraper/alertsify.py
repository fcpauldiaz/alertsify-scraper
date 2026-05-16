from __future__ import annotations

import logging
from typing import Any

import httpx
from pydantic import BaseModel, Field

from alertsify_scraper.config import Settings

logger = logging.getLogger(__name__)


class OptionPosition(BaseModel):
    id: str
    symbol: str
    ticker: str
    strike: float
    side: str
    expiration_label: str = Field(alias="expirationLabel")
    expiration_date: str = Field(alias="expirationDate")
    quantity: int
    entry_price: float = Field(alias="entryPrice")
    current_price: float = Field(alias="currentPrice")
    pnl: float
    option_type: str = Field(alias="optionType")
    is_broadcast: bool = Field(alias="isBroadcast")


class OptionPositionsResponse(BaseModel):
    success: bool
    positions: list[OptionPosition] = Field(default_factory=list)
    total: int | None = None


def _positions_url(settings: Settings) -> str:
    base = settings.alertsify_base_url.rstrip("/")
    return f"{base}/api/snaptrade/option-positions"


async def fetch_option_positions(
    client: httpx.AsyncClient,
    settings: Settings,
) -> OptionPositionsResponse:
    url = _positions_url(settings)
    headers: dict[str, str] = {}
    if settings.alertsify_authorization:
        headers["Authorization"] = settings.alertsify_authorization
    if settings.alertsify_cookie:
        headers["Cookie"] = settings.alertsify_cookie

    logger.info(
        "Fetching Alertsify positions from %s (auth=%s cookie=%s)",
        url,
        bool(settings.alertsify_authorization),
        bool(settings.alertsify_cookie),
    )
    response = await client.get(
        url,
        params={"userId": settings.alertsify_user_id},
        headers=headers,
    )
    response.raise_for_status()
    payload: dict[str, Any] = response.json()
    parsed = OptionPositionsResponse.model_validate(payload)
    if not parsed.success:
        msg = "Alertsify reported success=false"
        raise ValueError(msg)
    logger.info(
        "Alertsify returned %d position(s) (total=%s)",
        len(parsed.positions),
        parsed.total,
    )
    return parsed
