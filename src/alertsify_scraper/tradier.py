from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import httpx

from alertsify_scraper.alertsify import OptionPosition
from alertsify_scraper.config import Settings, TradierContext
from alertsify_scraper.sizing import OPTION_CONTRACT_MULTIPLIER

logger = logging.getLogger(__name__)

STRIKE_MAX_DIFF = 1e-3


def _tradier_headers(ctx: TradierContext) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {ctx.access_token}",
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
    ctx: TradierContext,
    underlying: str,
    expiration: str,
) -> list[dict[str, Any]]:
    base = ctx.api_base.rstrip("/")
    url = f"{base}/v1/markets/options/chains"
    logger.info(
        "Fetching Tradier chain mode=%s underlying=%s expiration=%s",
        ctx.mode,
        underlying,
        expiration,
    )
    response = await client.get(
        url,
        headers=_tradier_headers(ctx),
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


def _account_url(ctx: TradierContext, suffix: str) -> str:
    base = ctx.api_base.rstrip("/")
    return f"{base}/v1/accounts/{ctx.account_id}/{suffix}"


def _orders_url(ctx: TradierContext) -> str:
    return _account_url(ctx, "orders")


def _normalize_list_payload(raw: object) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if isinstance(raw, dict):
        return [raw]
    return []


async def fetch_account_balances(
    client: httpx.AsyncClient,
    ctx: TradierContext,
) -> dict[str, Any]:
    response = await client.get(
        _account_url(ctx, "balances"),
        headers=_tradier_headers(ctx),
    )
    response.raise_for_status()
    payload = response.json()
    balances = payload.get("balances")
    if isinstance(balances, dict):
        return balances
    return {}


async def fetch_account_positions(
    client: httpx.AsyncClient,
    ctx: TradierContext,
) -> list[dict[str, Any]]:
    response = await client.get(
        _account_url(ctx, "positions"),
        headers=_tradier_headers(ctx),
    )
    response.raise_for_status()
    payload = response.json()
    positions_block = payload.get("positions")
    if not isinstance(positions_block, dict):
        return []
    return _normalize_list_payload(positions_block.get("position"))


async def fetch_account_gainloss(
    client: httpx.AsyncClient,
    ctx: TradierContext,
    *,
    page: int = 1,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    response = await client.get(
        _account_url(ctx, "gainloss"),
        headers=_tradier_headers(ctx),
        params={"page": page, "limit": limit},
    )
    response.raise_for_status()
    payload = response.json()
    gainloss_block = payload.get("gainloss")
    if not isinstance(gainloss_block, dict):
        return []
    closed = gainloss_block.get("closed_position")
    return _normalize_list_payload(closed)


async def fetch_order(
    client: httpx.AsyncClient,
    ctx: TradierContext,
    order_id: str,
) -> dict[str, Any]:
    response = await client.get(
        f"{_orders_url(ctx)}/{order_id}",
        headers=_tradier_headers(ctx),
    )
    response.raise_for_status()
    payload = response.json()
    order = payload.get("order")
    if isinstance(order, dict):
        return order
    return {}


def _positive_float(value: object) -> float | None:
    if isinstance(value, (int, float)) and value > 0:
        return float(value)
    return None


def order_fill_premium_per_share(order: dict[str, Any]) -> float | None:
    status = order.get("status")
    if isinstance(status, str) and status.lower() in {"canceled", "cancelled", "rejected", "expired"}:
        return None
    fill = _positive_float(order.get("avg_fill_price"))
    if fill is not None:
        return fill
    leg = order.get("leg")
    legs = [leg] if isinstance(leg, dict) else leg if isinstance(leg, list) else []
    for row in legs:
        if isinstance(row, dict):
            leg_fill = _positive_float(row.get("avg_fill_price"))
            if leg_fill is not None:
                return leg_fill
    return None


def position_entry_premium_per_share(row: dict[str, Any]) -> float | None:
    cost_basis = row.get("cost_basis")
    quantity = row.get("quantity")
    if not isinstance(cost_basis, (int, float)) or not isinstance(quantity, (int, float)):
        return None
    if quantity == 0:
        return None
    return abs(float(cost_basis)) / (abs(float(quantity)) * OPTION_CONTRACT_MULTIPLIER)


async def fetch_orders_by_id(
    client: httpx.AsyncClient,
    ctx: TradierContext,
    order_ids: set[str],
) -> dict[str, dict[str, Any]]:
    ids = {order_id.strip() for order_id in order_ids if order_id.strip()}
    if not ids:
        return {}

    async def fetch_one(order_id: str) -> tuple[str, dict[str, Any]]:
        try:
            order = await fetch_order(client, ctx, order_id)
        except httpx.HTTPError:
            logger.warning("Failed fetching Tradier order id=%s", order_id)
            return order_id, {}
        return order_id, order


    results = await asyncio.gather(*(fetch_one(order_id) for order_id in ids))
    return {order_id: order for order_id, order in results if order}


def underlying_from_option_symbol(option_symbol: str) -> str:
    match = re.match(r"^([A-Z]+)", option_symbol)
    if not match:
        msg = f"Cannot parse underlying from option symbol {option_symbol!r}"
        raise ValueError(msg)
    return match.group(1)


async def _submit_option_order(
    client: httpx.AsyncClient,
    settings: Settings,
    ctx: TradierContext,
    *,
    underlying: str,
    option_symbol: str,
    quantity: int,
    side: str,
    preview: bool,
    action: str,
) -> str:
    url = _orders_url(ctx)
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

    submit_mode = "preview" if preview else ctx.mode
    logger.debug(
        "Submitting Tradier %s %s order underlying=%s option_symbol=%s qty=%s side=%s",
        submit_mode,
        action,
        underlying,
        option_symbol,
        quantity,
        side,
    )
    response = await client.post(
        url,
        headers={
            **_tradier_headers(ctx),
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
    logger.debug(
        "Tradier %s order accepted id=%s status=%s",
        submit_mode,
        order_id_str,
        order.get("status"),
    )
    return order_id_str


async def place_option_order(
    client: httpx.AsyncClient,
    settings: Settings,
    ctx: TradierContext,
    *,
    underlying: str,
    option_symbol: str,
    quantity: int,
    preview: bool,
) -> str:
    return await _submit_option_order(
        client,
        settings,
        ctx,
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
    ctx: TradierContext,
    *,
    underlying: str,
    option_symbol: str,
    quantity: int,
    preview: bool,
) -> str:
    return await _submit_option_order(
        client,
        settings,
        ctx,
        underlying=underlying,
        option_symbol=option_symbol,
        quantity=quantity,
        side=settings.tradier_option_close_side,
        preview=preview,
        action="close",
    )
