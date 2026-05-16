from __future__ import annotations

import logging
from typing import Any

import httpx
from pydantic import BaseModel, Field

from alertsify_scraper.config import Settings

logger = logging.getLogger(__name__)

_DEFAULT_ALERTSIFY_USER_AGENT = "curl/8.7.1"


def _alertsify_headers(settings: Settings) -> dict[str, str]:
    headers: dict[str, str] = {
        "Accept": "*/*",
        "User-Agent": settings.alertsify_user_agent or _DEFAULT_ALERTSIFY_USER_AGENT,
    }
    if settings.alertsify_authorization:
        headers["Authorization"] = settings.alertsify_authorization
    if settings.alertsify_cookie:
        headers["Cookie"] = settings.alertsify_cookie
    return headers


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
    headers = _alertsify_headers(settings)

    cookie_len = len(settings.alertsify_cookie) if settings.alertsify_cookie else 0
    logger.info(
        "Fetching Alertsify positions from %s (auth=%s cookie_len=%d follow_redirects=True)",
        url,
        bool(settings.alertsify_authorization),
        cookie_len,
    )
    response = await client.get(
        url,
        params={"userId": settings.alertsify_user_id},
        headers=headers,
        follow_redirects=True,
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
