from __future__ import annotations

import logging

import httpx

from alertsify_scraper.alertsify import OptionPosition
from alertsify_scraper.config import Settings

logger = logging.getLogger(__name__)


async def notify_trade_placed(
    client: httpx.AsyncClient,
    settings: Settings,
    *,
    position: OptionPosition,
    tradier_option_symbol: str,
    tradier_order_id: str,
) -> None:
    base = settings.ntfy_base_url.rstrip("/")
    topic = settings.ntfy_topic.strip("/")
    url = f"{base}/{topic}"
    title = "Tradier option order placed"
    body = (
        f"{position.ticker} {position.option_type} "
        f"{position.expiration_date} @{position.strike} x{position.quantity}\n"
        f"option_symbol={tradier_option_symbol}\n"
        f"tradier_order_id={tradier_order_id}\n"
        f"alertsify_id={position.id}"
    )
    logger.info("Sending ntfy notification to %s", url)
    response = await client.post(
        url,
        content=body,
        headers={"Title": title, "Content-Type": "text/plain; charset=utf-8"},
    )
    response.raise_for_status()
    logger.info("ntfy notification sent status=%s", response.status_code)
