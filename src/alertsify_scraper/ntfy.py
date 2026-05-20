from __future__ import annotations

import logging

import httpx

from alertsify_scraper.alertsify import OptionPosition
from alertsify_scraper.config import Settings

logger = logging.getLogger(__name__)


async def _post_notification(
    client: httpx.AsyncClient,
    settings: Settings,
    *,
    title: str,
    body: str,
) -> None:
    base = settings.ntfy_base_url.rstrip("/")
    topic = settings.ntfy_topic.strip("/")
    url = f"{base}/{topic}"
    logger.info("Sending ntfy notification to %s", url)
    response = await client.post(
        url,
        content=body,
        headers={"Title": title, "Content-Type": "text/plain; charset=utf-8"},
    )
    response.raise_for_status()
    logger.info("ntfy notification sent status=%s", response.status_code)


async def notify_trade_placing(
    client: httpx.AsyncClient,
    settings: Settings,
    *,
    alertsify_user_id: str,
    position: OptionPosition,
    tradier_option_symbol: str,
    order_quantity: int,
    preview: bool,
) -> None:
    mode = "preview" if preview else "live"
    title = "Submitting Tradier option order"
    body = (
        f"About to submit {mode} open order.\n"
        f"{position.ticker} {position.option_type} "
        f"{position.expiration_date} @{position.strike} "
        f"order_qty={order_quantity} (alertsify_qty={position.quantity})\n"
        f"alertsify_user_id={alertsify_user_id}\n"
        f"option_symbol={tradier_option_symbol}\n"
        f"alertsify_id={position.id}"
    )
    await _post_notification(client, settings, title=title, body=body)


async def notify_trade_closing(
    client: httpx.AsyncClient,
    settings: Settings,
    *,
    alertsify_user_id: str,
    alertsify_position_id: str,
    alertsify_symbol: str,
    tradier_option_symbol: str,
    quantity: int,
    preview: bool,
) -> None:
    mode = "preview" if preview else "live"
    title = "Submitting Tradier option close"
    body = (
        f"About to submit {mode} close order (position removed from Alertsify).\n"
        f"alertsify_user_id={alertsify_user_id}\n"
        f"alertsify_id={alertsify_position_id}\n"
        f"symbol={alertsify_symbol}\n"
        f"option_symbol={tradier_option_symbol}\n"
        f"quantity={quantity}"
    )
    await _post_notification(client, settings, title=title, body=body)
