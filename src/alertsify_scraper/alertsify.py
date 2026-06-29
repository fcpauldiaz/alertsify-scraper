from __future__ import annotations

import logging
from typing import Any

import httpx
from pydantic import BaseModel, Field, ValidationError, field_validator

from alertsify_scraper.config import Settings

logger = logging.getLogger(__name__)

_DEFAULT_ALERTSIFY_USER_AGENT = "curl/8.7.1"
# Alertsify option premiums are cents per share (210 -> $2.10).
ALERTSIFY_PRICE_CENTS_PER_DOLLAR = 100


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
    current_price: float | None = Field(default=None, alias="currentPrice")
    pnl: float | None = None
    option_type: str = Field(alias="optionType")
    is_broadcast: bool = Field(alias="isBroadcast")

    @field_validator("entry_price", mode="before")
    @classmethod
    def entry_price_cents_to_dollars_per_share(cls, value: object) -> object:
        if isinstance(value, (int, float)):
            return float(value) / ALERTSIFY_PRICE_CENTS_PER_DOLLAR
        return value


class OptionPositionsResponse(BaseModel):
    success: bool
    positions: list[OptionPosition] = Field(default_factory=list)
    total: int | None = None

    @classmethod
    def from_api_payload(cls, payload: dict[str, Any]) -> OptionPositionsResponse:
        raw_positions = payload.get("positions")
        if not isinstance(raw_positions, list):
            raw_positions = []

        positions: list[OptionPosition] = []
        for index, raw in enumerate(raw_positions):
            try:
                positions.append(OptionPosition.model_validate(raw))
            except ValidationError as exc:
                position_id = raw.get("id", "?") if isinstance(raw, dict) else "?"
                logger.warning(
                    "Skipping invalid Alertsify position index=%d id=%s: %s",
                    index,
                    position_id,
                    exc.errors(include_url=False),
                )

        return cls(
            success=bool(payload.get("success")),
            positions=positions,
            total=payload.get("total") if isinstance(payload.get("total"), int) else None,
        )


def _positions_url(settings: Settings) -> str:
    base = settings.alertsify_base_url.rstrip("/")
    return f"{base}/api/snaptrade/option-positions"


async def fetch_option_positions(
    client: httpx.AsyncClient,
    settings: Settings,
    user_id: str,
) -> OptionPositionsResponse:
    url = _positions_url(settings)
    headers = _alertsify_headers(settings)

    cookie_len = len(settings.alertsify_cookie) if settings.alertsify_cookie else 0
    logger.info(
        "Fetching Alertsify positions user_id=%s from %s "
        "(auth=%s cookie_len=%d follow_redirects=True)",
        user_id,
        url,
        bool(settings.alertsify_authorization),
        cookie_len,
    )
    response = await client.get(
        url,
        params={"userId": user_id},
        headers=headers,
        follow_redirects=True,
    )
    response.raise_for_status()
    payload: dict[str, Any] = response.json()
    parsed = OptionPositionsResponse.from_api_payload(payload)
    if not parsed.success:
        msg = f"Alertsify reported success=false for user_id={user_id}"
        raise ValueError(msg)
    logger.debug(
        "Alertsify user_id=%s returned %d position(s) (total=%s)",
        user_id,
        len(parsed.positions),
        parsed.total,
    )
    return parsed


async def fetch_all_option_positions(
    client: httpx.AsyncClient,
    settings: Settings,
) -> list[tuple[str, OptionPositionsResponse]]:
    results: list[tuple[str, OptionPositionsResponse]] = []
    for user_id in settings.alertsify_user_ids:
        try:
            parsed = await fetch_option_positions(client, settings, user_id)
            results.append((user_id, parsed))
        except Exception:
            logger.exception("Failed fetching Alertsify positions for user_id=%s", user_id)
    return results
