from __future__ import annotations

from typing import Any

from alertsify_scraper.alertsify import OptionPosition
from alertsify_scraper.config import Settings

OPTION_CONTRACT_MULTIPLIER = 100
MAX_ALERT_CHAIN_PREMIUM_DRIFT = 0.10


def find_chain_row(
    chain: list[dict[str, Any]],
    option_symbol: str,
) -> dict[str, Any] | None:
    for row in chain:
        sym = row.get("symbol")
        if isinstance(sym, str) and sym == option_symbol:
            return row
    return None


def _positive_price(value: object) -> float | None:
    if isinstance(value, (int, float)) and value > 0:
        return float(value)
    return None


def premium_per_share_from_chain(
    chain_row: dict[str, Any] | None,
    *,
    fallback_price: float | None = None,
) -> float | None:
    if chain_row is not None:
        ask = _positive_price(chain_row.get("ask"))
        if ask is not None:
            return ask

        last = _positive_price(chain_row.get("last"))
        if last is not None:
            return last

        bid = _positive_price(chain_row.get("bid"))
        ask_raw = chain_row.get("ask")
        if bid is not None and isinstance(ask_raw, (int, float)) and ask_raw > 0:
            return (bid + float(ask_raw)) / 2.0

        if bid is not None:
            return bid

    if fallback_price is not None and fallback_price > 0:
        return fallback_price

    return None


def chain_premium_per_share(
    chain: list[dict[str, Any]],
    option_symbol: str,
) -> float | None:
    chain_row = find_chain_row(chain, option_symbol)
    return premium_per_share_from_chain(chain_row)


def premium_drift_from_alert(
    chain: list[dict[str, Any]],
    option_symbol: str,
    position: OptionPosition,
) -> float | None:
    chain_premium = chain_premium_per_share(chain, option_symbol)
    if chain_premium is None or position.entry_price <= 0:
        return None
    return abs(chain_premium - position.entry_price)


def premium_per_share_for_open(
    settings: Settings,
    chain: list[dict[str, Any]],
    option_symbol: str,
    position: OptionPosition,
) -> float | None:
    if settings.tradier_order_type == "limit" and settings.tradier_limit_price is not None:
        return settings.tradier_limit_price

    chain_row = find_chain_row(chain, option_symbol)
    fallback = position.current_price if position.current_price > 0 else None
    return premium_per_share_from_chain(chain_row, fallback_price=fallback)


def contracts_from_capital(max_capital: float, premium_per_share: float) -> int:
    if premium_per_share <= 0:
        return 0
    cost_per_contract = premium_per_share * OPTION_CONTRACT_MULTIPLIER
    if cost_per_contract <= 0:
        return 0
    return int(max_capital // cost_per_contract)


def resolve_open_quantity(
    settings: Settings,
    chain: list[dict[str, Any]],
    option_symbol: str,
    position: OptionPosition,
) -> tuple[int, float | None, int]:
    premium = premium_per_share_for_open(settings, chain, option_symbol, position)
    if premium is None:
        return 0, None, 0
    capital_cap = contracts_from_capital(settings.trade_max_capital, premium)
    alertsify_qty = max(position.quantity, 0)
    quantity = min(alertsify_qty, capital_cap) if alertsify_qty > 0 else 0
    return quantity, premium, capital_cap
