from __future__ import annotations

import asyncio
import logging
import signal
from collections.abc import Callable
from functools import partial
from typing import Any, TypeVar

import httpx
from pydantic import ValidationError

from alertsify_scraper import alertsify, db, ntfy, tradier
from alertsify_scraper.config import Settings

logger = logging.getLogger(__name__)

T = TypeVar("T")


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


async def _run_in_thread(fn: Callable[[], T]) -> T:
    return await asyncio.to_thread(fn)


async def run_poll_cycle(client: httpx.AsyncClient, settings: Settings) -> None:
    logger.info("Poll cycle started")
    parsed = await alertsify.fetch_option_positions(client, settings)
    chain_cache: dict[tuple[str, str], list[dict[str, Any]]] = {}

    async def get_chain(under: str, exp: str) -> list[dict[str, Any]]:
        key = (under, exp)
        if key not in chain_cache:
            chain_cache[key] = await tradier.fetch_option_chain(
                client,
                settings,
                under,
                exp,
            )
            logger.info(
                "Chain loaded underlying=%s expiration=%s contracts=%d",
                under,
                exp,
                len(chain_cache[key]),
            )
        return chain_cache[key]

    placed = 0
    skipped_dup = 0
    errors = 0

    for pos in parsed.positions:
        try:
            if await _run_in_thread(partial(db.has_placed_sync, settings, pos.id)):
                skipped_dup += 1
                logger.info(
                    "skip duplicate alertsify_position_id=%s symbol=%s",
                    pos.id,
                    pos.symbol,
                )
                continue

            chain = await get_chain(pos.ticker, pos.expiration_date)
            option_symbol = tradier.resolve_tradier_option_symbol(chain, pos)
            logger.info(
                "Resolved Tradier option_symbol=%s for alertsify_id=%s",
                option_symbol,
                pos.id,
            )

            preview = settings.tradier_preview_only
            order_id = await tradier.place_option_order(
                client,
                settings,
                underlying=pos.ticker,
                option_symbol=option_symbol,
                quantity=pos.quantity,
                preview=preview,
            )
            if preview:
                logger.info(
                    "Preview only enabled; skipping DB persist and ntfy "
                    "(alertsify_id=%s tradier_order_id=%s)",
                    pos.id,
                    order_id,
                )
                continue

            await _run_in_thread(
                partial(
                    db.record_placed_sync,
                    settings,
                    alertsify_position_id=pos.id,
                    alertsify_symbol=pos.symbol,
                    tradier_option_symbol=option_symbol,
                    tradier_order_id=order_id,
                    quantity=pos.quantity,
                ),
            )
            try:
                await ntfy.notify_trade_placed(
                    client,
                    settings,
                    position=pos,
                    tradier_option_symbol=option_symbol,
                    tradier_order_id=order_id,
                )
            except Exception:
                logger.exception(
                    "ntfy failed after successful placement alertsify_id=%s",
                    pos.id,
                )
            placed += 1
        except Exception:
            errors += 1
            logger.exception("Failed processing position id=%s", pos.id)

    logger.info(
        "Poll cycle finished positions=%d placed=%d skipped_dup=%d errors=%d",
        len(parsed.positions),
        placed,
        skipped_dup,
        errors,
    )


async def async_main() -> None:
    settings = Settings()
    configure_logging()
    await _run_in_thread(partial(db.migrate_sync, settings))

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    timeout = httpx.Timeout(60.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        while not stop.is_set():
            try:
                await run_poll_cycle(client, settings)
            except Exception:
                logger.exception("Poll cycle aborted by error")

            try:
                await asyncio.wait_for(
                    stop.wait(),
                    timeout=settings.poll_interval_ms / 1000.0,
                )
            except asyncio.TimeoutError:
                continue

    logger.info("Shutdown requested; exiting")


def main() -> None:
    try:
        asyncio.run(async_main())
    except ValidationError as exc:
        configure_logging()
        logger.error("Invalid configuration: %s", exc)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
