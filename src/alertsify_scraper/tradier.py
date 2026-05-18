from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from alertsify_scraper.alertsify import OptionPosition
from alertsify_scraper.config import Settings

logger = logging.getLogger(__name__)

STRIKE_MAX_DIFF = 1e-3


def _tradier_headers(settings: Settings) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.tradier_access_token}",
        "Accept": "application/json",
    }


def _normalize_option_list(options_payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not options_payload:
        return []
    raw = options_payload.get("option")
    if raw is None:
        return []
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if isinstance(raw, dict):
        return [raw]
    return []


async def fetch_option_chain(
    client: httpx.AsyncClient,
    settings: Settings,
    underlying: str,
    expiration: str,
) -> list[dict[str, Any]]:
    base = settings.tradier_api_base.rstrip("/")
    url = f"{base}/v1/markets/options/chains"
    logger.info(
        "Fetching Tradier chain underlying=%s expiration=%s",
        underlying,
        expiration,
    )
    response = await client.get(
        url,
        headers=_tradier_headers(settings),
        params={"symbol": underlying, "expiration": expiration},
    )
    response.raise_for_status()
    data = response.json()
    options_block = data.get("options")
    if not isinstance(options_block, dict):
        return []
    return _normalize_option_list(options_block)


def chain_option_type_to_alertsify(option_type: str | None) -> str | None:
    if option_type is None:
        return None
    lowered = option_type.lower()
    if lowered == "call":
        return "CALL"
    if lowered == "put":
        return "PUT"
    return None


def resolve_tradier_option_symbol(
    chain: list[dict[str, Any]],
    position: OptionPosition,
) -> str:
    want_type = position.option_type.upper()
    best: tuple[float, str] | None = None
    for row in chain:
        strike = row.get("strike")
        if not isinstance(strike, (int, float)):
            continue
        diff = abs(float(strike) - float(position.strike))
        if diff > STRIKE_MAX_DIFF:
            continue
        mapped = chain_option_type_to_alertsify(row.get("option_type"))
        if mapped != want_type:
            continue
        sym = row.get("symbol")
        if not isinstance(sym, str) or not sym:
            continue
        if best is None or diff < best[0]:
            best = (diff, sym)
    if best is None:
        msg = (
            f"No Tradier contract for {position.ticker} "
            f"{position.expiration_date} {want_type} @{position.strike}"
        )
        raise LookupError(msg)
    return best[1]


def _orders_url(settings: Settings) -> str:
    base = settings.tradier_api_base.rstrip("/")
    return f"{base}/v1/accounts/{settings.tradier_account_id}/orders"


def underlying_from_option_symbol(option_symbol: str) -> str:
    match = re.match(r"^([A-Z]+)", option_symbol)
    if not match:
        msg = f"Cannot parse underlying from option symbol {option_symbol!r}"
        raise ValueError(msg)
    return match.group(1)


async def _submit_option_order(
    client: httpx.AsyncClient,
    settings: Settings,
    *,
    underlying: str,
    option_symbol: str,
    quantity: int,
    side: str,
    preview: bool,
    action: str,
) -> str:
    url = _orders_url(settings)
    form: dict[str, str | int | float] = {
        "class": "option",
        "symbol": underlying,
        "option_symbol": option_symbol,
        "side": side,
        "quantity": quantity,
        "type": settings.tradier_order_type,
        "duration": settings.tradier_order_duration,
    }
    if settings.tradier_order_type == "limit":
        form["price"] = float(settings.tradier_limit_price or 0)
    if preview:
        form["preview"] = "true"

    mode = "preview" if preview else "live"
    logger.info(
        "Submitting Tradier %s %s order underlying=%s option_symbol=%s qty=%s side=%s",
        mode,
        action,
        underlying,
        option_symbol,
        quantity,
        side,
    )
    response = await client.post(
        url,
        headers={
            **_tradier_headers(settings),
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data=form,
    )
    response.raise_for_status()
    payload = response.json()
    order = payload.get("order")
    if not isinstance(order, dict):
        msg = f"Unexpected Tradier order response: {payload!r}"
        raise ValueError(msg)
    order_id = order.get("id")
    if order_id is None:
        msg = f"Tradier order missing id: {payload!r}"
        raise ValueError(msg)
    order_id_str = str(order_id)
    logger.info(
        "Tradier %s order accepted id=%s status=%s",
        mode,
        order_id_str,
        order.get("status"),
    )
    return order_id_str


async def place_option_order(
    client: httpx.AsyncClient,
    settings: Settings,
    *,
    underlying: str,
    option_symbol: str,
    quantity: int,
    preview: bool,
) -> str:
    return await _submit_option_order(
        client,
        settings,
        underlying=underlying,
        option_symbol=option_symbol,
        quantity=quantity,
        side=settings.tradier_option_side,
        preview=preview,
        action="open",
    )


async def close_option_order(
    client: httpx.AsyncClient,
    settings: Settings,
    *,
    underlying: str,
    option_symbol: str,
    quantity: int,
    preview: bool,
) -> str:
    return await _submit_option_order(
        client,
        settings,
        underlying=underlying,
        option_symbol=option_symbol,
        quantity=quantity,
        side=settings.tradier_option_close_side,
        preview=preview,
        action="close",
    )
