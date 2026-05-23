from __future__ import annotations

import logging
from typing import Literal

import httpx

from alertsify_scraper.alertsify import OptionPosition
from alertsify_scraper.config import Settings
from alertsify_scraper.sizing import (
    MAX_ALERT_CHAIN_PREMIUM_DRIFT,
    OPTION_CONTRACT_MULTIPLIER,
)

logger = logging.getLogger(__name__)

NtfyPriority = Literal["min", "low", "default", "high", "max", "urgent"]
SkipReason = Literal[
    "drift_unavailable",
    "drift_exceeded",
    "no_premium",
    "quantity_below_cap",
]

_SKIP_REASON_HEADLINE: dict[SkipReason, str] = {
    "drift_unavailable": "Cannot compare chain premium to alert entry",
    "drift_exceeded": (
        f"Chain drift exceeds ${MAX_ALERT_CHAIN_PREMIUM_DRIFT:.2f} limit"
    ),
    "no_premium": "No valid premium on chain or Alertsify",
    "quantity_below_cap": "Order size below 1 contract after capital cap",
}


def _fmt_price(value: float | None) -> str:
    if value is None:
        return "—"
    return f"${value:.2f}"


def _fmt_contract(
    *,
    ticker: str,
    option_type: str,
    strike: float,
    expiration_date: str,
    expiration_label: str | None = None,
) -> str:
    type_label = option_type.strip().upper() or "OPTION"
    strike_text = f"{strike:g}"
    expiry = expiration_label.strip() if expiration_label else expiration_date
    return f"**{ticker} ${strike_text} {type_label}** · {expiry}"


def _fmt_mode(preview: bool) -> str:
    return "PREVIEW" if preview else "LIVE"


def _fmt_user_short(user_id: str) -> str:
    trimmed = user_id.strip()
    if len(trimmed) <= 12:
        return trimmed
    return f"{trimmed[:8]}…{trimmed[-3:]}"


def _estimated_order_cost(quantity: int, premium_per_share: float) -> float:
    return quantity * premium_per_share * OPTION_CONTRACT_MULTIPLIER


def _order_line(settings: Settings, quantity: int, premium_per_share: float) -> str:
    if settings.tradier_order_type == "limit" and settings.tradier_limit_price is not None:
        price_part = f"limit @ {_fmt_price(settings.tradier_limit_price)}"
    else:
        price_part = f"market (~{_fmt_price(premium_per_share)}/share)"
    return (
        f"`{settings.tradier_option_side}` × **{quantity}** · "
        f"{settings.tradier_order_type} · {price_part} · {settings.tradier_order_duration}"
    )


def _markdown_section(title: str, lines: list[str]) -> str:
    body = "\n".join(f"- {line}" for line in lines if line)
    return f"**{title}**\n{body}"


async def _post_notification(
    client: httpx.AsyncClient,
    settings: Settings,
    *,
    title: str,
    body: str,
    tags: list[str],
    priority: NtfyPriority,
) -> None:
    base = settings.ntfy_base_url.rstrip("/")
    topic = settings.ntfy_topic.strip("/")
    url = f"{base}/{topic}"
    logger.debug("Sending ntfy notification to %s", url)
    response = await client.post(
        url,
        content=body,
        headers={
            "Title": title,
            "Tags": ",".join(tags),
            "Priority": priority,
            "Markdown": "yes",
            "Content-Type": "text/markdown; charset=utf-8",
        },
    )
    response.raise_for_status()
    logger.debug("ntfy notification sent status=%s", response.status_code)


async def notify_trade_placing(
    client: httpx.AsyncClient,
    settings: Settings,
    *,
    alertsify_user_id: str,
    position: OptionPosition,
    tradier_option_symbol: str,
    order_quantity: int,
    premium_per_share: float,
    chain_premium: float | None,
    drift: float | None,
    preview: bool,
) -> None:
    mode = _fmt_mode(preview)
    contract = _fmt_contract(
        ticker=position.ticker,
        option_type=position.option_type,
        strike=position.strike,
        expiration_date=position.expiration_date,
        expiration_label=position.expiration_label,
    )
    est_cost = _estimated_order_cost(order_quantity, premium_per_share)

    pricing_lines = [f"Alert entry: **{_fmt_price(position.entry_price)}**"]
    if chain_premium is not None:
        pricing_lines.append(f"Chain: **{_fmt_price(chain_premium)}**")
    if drift is not None:
        pricing_lines.append(f"Drift: **{_fmt_price(drift)}**")
    if position.current_price > 0:
        pricing_lines.append(f"Alertsify mark: {_fmt_price(position.current_price)}")

    title = f"{mode} OPEN · {position.ticker} {position.option_type.upper()}"
    body = "\n\n".join(
        [
            contract,
            _markdown_section("Pricing", pricing_lines),
            _markdown_section(
                "Order",
                [
                    _order_line(settings, order_quantity, premium_per_share),
                    f"Alertsify qty **{position.quantity}** → order **{order_quantity}**",
                    f"Est. cost **~{_fmt_price(est_cost)}** (max capital {_fmt_price(settings.trade_max_capital)})",
                ],
            ),
            _markdown_section(
                "Refs",
                [
                    f"User `{_fmt_user_short(alertsify_user_id)}`",
                    f"Alertsify `{position.id}`",
                    f"Tradier `{tradier_option_symbol}`",
                    f"Symbol `{position.symbol}`",
                ],
            ),
        ],
    )
    tags = ["chart_with_upwards_trend", "moneybag"]
    if preview:
        tags.insert(0, "test_tube")
    priority: NtfyPriority = "low" if preview else "high"
    await _post_notification(
        client,
        settings,
        title=title,
        body=body,
        tags=tags,
        priority=priority,
    )


def _skip_detail_lines(
    reason: SkipReason,
    *,
    position: OptionPosition,
    chain_premium: float | None,
    drift: float | None,
    premium_per_share: float | None,
    capital_cap: int | None,
    cost_per_contract: float | None,
    max_capital: float,
) -> list[str]:
    lines = [f"Alert entry: **{_fmt_price(position.entry_price)}**"]
    if chain_premium is not None:
        lines.append(f"Chain: **{_fmt_price(chain_premium)}**")
    elif reason in ("drift_unavailable", "no_premium"):
        lines.append("Chain: — (no quote)")

    if drift is not None:
        lines.append(f"Drift: **{_fmt_price(drift)}**")
    if reason == "drift_exceeded":
        lines.append(f"Max allowed: **{_fmt_price(MAX_ALERT_CHAIN_PREMIUM_DRIFT)}**")

    if reason == "no_premium":
        if position.current_price > 0:
            lines.append(f"Alertsify mark: {_fmt_price(position.current_price)}")
        lines.append(f"Alertsify qty: **{position.quantity}**")

    if reason == "quantity_below_cap" and premium_per_share is not None:
        lines.append(f"Premium used: **{_fmt_price(premium_per_share)}**/share")
        lines.append(f"Cost/contract: **{_fmt_price(cost_per_contract)}**")
        lines.append(f"Max capital: **{_fmt_price(max_capital)}**")
        lines.append(f"Capital cap: **{capital_cap or 0}** contracts")
        lines.append(f"Alertsify qty: **{position.quantity}**")

    return lines


async def notify_trade_skipped(
    client: httpx.AsyncClient,
    settings: Settings,
    *,
    alertsify_user_id: str,
    position: OptionPosition,
    tradier_option_symbol: str,
    reason: SkipReason,
    chain_premium: float | None = None,
    drift: float | None = None,
    premium_per_share: float | None = None,
    capital_cap: int | None = None,
    cost_per_contract: float | None = None,
) -> None:
    contract = _fmt_contract(
        ticker=position.ticker,
        option_type=position.option_type,
        strike=position.strike,
        expiration_date=position.expiration_date,
        expiration_label=position.expiration_label,
    )
    headline = _SKIP_REASON_HEADLINE[reason]
    title = f"SKIP OPEN · {position.ticker} {position.option_type.upper()}"
    body = "\n\n".join(
        [
            contract,
            f"**{headline}**",
            _markdown_section(
                "Details",
                _skip_detail_lines(
                    reason,
                    position=position,
                    chain_premium=chain_premium,
                    drift=drift,
                    premium_per_share=premium_per_share,
                    capital_cap=capital_cap,
                    cost_per_contract=cost_per_contract,
                    max_capital=settings.trade_max_capital,
                ),
            ),
            _markdown_section(
                "Refs",
                [
                    f"User `{_fmt_user_short(alertsify_user_id)}`",
                    f"Alertsify `{position.id}`",
                    f"Tradier `{tradier_option_symbol}`",
                    f"Symbol `{position.symbol}`",
                ],
            ),
        ],
    )
    await _post_notification(
        client,
        settings,
        title=title,
        body=body,
        tags=["warning", "no_entry"],
        priority="default",
    )


async def notify_trade_closing(
    client: httpx.AsyncClient,
    settings: Settings,
    *,
    alertsify_user_id: str,
    alertsify_position_id: str,
    alertsify_symbol: str,
    underlying: str,
    tradier_option_symbol: str,
    quantity: int,
    preview: bool,
) -> None:
    mode = _fmt_mode(preview)
    title = f"{mode} CLOSE · {underlying}"
    body = "\n\n".join(
        [
            f"Position removed from Alertsify — closing on Tradier.",
            _markdown_section(
                "Close",
                [
                    f"`{settings.tradier_option_close_side}` × **{quantity}** · "
                    f"{settings.tradier_order_type} · {settings.tradier_order_duration}",
                    f"Underlying **{underlying}**",
                    f"Symbol `{alertsify_symbol}`",
                ],
            ),
            _markdown_section(
                "Refs",
                [
                    f"User `{_fmt_user_short(alertsify_user_id)}`",
                    f"Alertsify `{alertsify_position_id}`",
                    f"Tradier `{tradier_option_symbol}`",
                ],
            ),
        ],
    )
    tags = ["chart_with_downwards_trend"]
    if preview:
        tags.insert(0, "test_tube")
    priority: NtfyPriority = "low" if preview else "high"
    await _post_notification(
        client,
        settings,
        title=title,
        body=body,
        tags=tags,
        priority=priority,
    )
