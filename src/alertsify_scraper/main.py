from __future__ import annotations

import asyncio
import logging
import signal
from collections.abc import Callable
from datetime import datetime, timedelta
from functools import partial
from typing import Any, TypeVar
from zoneinfo import ZoneInfo

import httpx
from pydantic import ValidationError

from alertsify_scraper import alertsify, db, market_hours, ntfy, sizing, tradier
from alertsify_scraper.db import OpenTrade
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


async def _sleep_until_or_stop(
    stop: asyncio.Event,
    seconds: float,
    *,
    max_chunk_s: float = 300.0,
) -> bool:
    remaining = seconds
    while remaining > 0 and not stop.is_set():
        chunk = min(remaining, max_chunk_s)
        try:
            await asyncio.wait_for(stop.wait(), timeout=chunk)
            return True
        except asyncio.TimeoutError:
            remaining -= chunk
    return stop.is_set()


async def run_poll_cycle(client: httpx.AsyncClient, settings: Settings) -> None:
    logger.info(
        "Poll cycle started for %d Alertsify user(s)",
        len(settings.alertsify_user_ids),
    )
    user_results = await alertsify.fetch_all_option_positions(client, settings)
    user_fetch_errors = len(settings.alertsify_user_ids) - len(user_results)
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
    closed = 0
    skipped_dup = 0
    skipped_drift = 0
    errors = 0
    total_positions = 0

    async def close_trade(user_id: str, trade: OpenTrade) -> None:
        nonlocal closed, errors
        underlying = trade.underlying or tradier.underlying_from_option_symbol(
            trade.tradier_option_symbol,
        )
        preview = settings.tradier_preview_only
        try:
            await ntfy.notify_trade_closing(
                client,
                settings,
                alertsify_user_id=user_id,
                alertsify_position_id=trade.alertsify_position_id,
                alertsify_symbol=trade.alertsify_symbol,
                underlying=underlying,
                tradier_option_symbol=trade.tradier_option_symbol,
                quantity=trade.quantity,
                preview=preview,
            )
        except Exception:
            logger.exception(
                "ntfy failed before close user_id=%s alertsify_id=%s",
                user_id,
                trade.alertsify_position_id,
            )
        logger.info(
            "Closing Tradier position user_id=%s alertsify_id=%s option_symbol=%s",
            user_id,
            trade.alertsify_position_id,
            trade.tradier_option_symbol,
        )
        close_order_id = await tradier.close_option_order(
            client,
            settings,
            underlying=underlying,
            option_symbol=trade.tradier_option_symbol,
            quantity=trade.quantity,
            preview=preview,
        )
        if preview:
            logger.info(
                "Preview only enabled; skipping DB close "
                "(user_id=%s alertsify_id=%s close_order_id=%s)",
                user_id,
                trade.alertsify_position_id,
                close_order_id,
            )
            return
        await _run_in_thread(
            partial(
                db.mark_closed_sync,
                settings,
                alertsify_user_id=user_id,
                alertsify_position_id=trade.alertsify_position_id,
                tradier_close_order_id=close_order_id,
            ),
        )
        closed += 1

    for user_id, parsed in user_results:
        total_positions += len(parsed.positions)
        api_position_ids = {pos.id for pos in parsed.positions}

        open_trades = await _run_in_thread(
            partial(db.list_open_trades_sync, settings, user_id),
        )
        for trade in open_trades:
            if trade.alertsify_position_id in api_position_ids:
                continue
            try:
                await close_trade(user_id, trade)
            except Exception:
                errors += 1
                logger.exception(
                    "Failed closing user_id=%s position id=%s",
                    user_id,
                    trade.alertsify_position_id,
                )

        for pos in parsed.positions:
            try:
                if await _run_in_thread(
                    partial(db.has_open_placed_sync, settings, user_id, pos.id),
                ):
                    skipped_dup += 1
                    logger.info(
                        "skip duplicate user_id=%s alertsify_position_id=%s symbol=%s",
                        user_id,
                        pos.id,
                        pos.symbol,
                    )
                    continue

                chain = await get_chain(pos.ticker, pos.expiration_date)
                option_symbol = tradier.resolve_tradier_option_symbol(chain, pos)
                logger.info(
                    "Resolved Tradier option_symbol=%s for user_id=%s alertsify_id=%s",
                    option_symbol,
                    user_id,
                    pos.id,
                )

                drift = sizing.premium_drift_from_alert(chain, option_symbol, pos)
                chain_premium = sizing.chain_premium_per_share(chain, option_symbol)
                if drift is None:
                    skipped_drift += 1
                    logger.warning(
                        "Skip open: cannot compare chain premium to alert entry "
                        "user_id=%s alertsify_id=%s option_symbol=%s entry_price=%s",
                        user_id,
                        pos.id,
                        option_symbol,
                        pos.entry_price,
                    )
                    try:
                        await ntfy.notify_trade_skipped(
                            client,
                            settings,
                            alertsify_user_id=user_id,
                            position=pos,
                            tradier_option_symbol=option_symbol,
                            reason="drift_unavailable",
                            chain_premium=chain_premium,
                        )
                    except Exception:
                        logger.exception(
                            "ntfy failed on drift_unavailable skip user_id=%s alertsify_id=%s",
                            user_id,
                            pos.id,
                        )
                    continue
                if drift > sizing.MAX_ALERT_CHAIN_PREMIUM_DRIFT:
                    skipped_drift += 1
                    logger.warning(
                        "Skip open: chain premium drift exceeds %.2f "
                        "user_id=%s alertsify_id=%s option_symbol=%s "
                        "chain_premium=%s entry_price=%s drift=%s",
                        sizing.MAX_ALERT_CHAIN_PREMIUM_DRIFT,
                        user_id,
                        pos.id,
                        option_symbol,
                        chain_premium,
                        pos.entry_price,
                        drift,
                    )
                    try:
                        await ntfy.notify_trade_skipped(
                            client,
                            settings,
                            alertsify_user_id=user_id,
                            position=pos,
                            tradier_option_symbol=option_symbol,
                            reason="drift_exceeded",
                            chain_premium=chain_premium,
                            drift=drift,
                        )
                    except Exception:
                        logger.exception(
                            "ntfy failed on drift_exceeded skip user_id=%s alertsify_id=%s",
                            user_id,
                            pos.id,
                        )
                    continue

                quantity, premium, capital_cap = sizing.resolve_open_quantity(
                    settings,
                    chain,
                    option_symbol,
                    pos,
                )
                if premium is None:
                    logger.warning(
                        "Skip open: no valid premium user_id=%s alertsify_id=%s "
                        "option_symbol=%s alertsify_qty=%s",
                        user_id,
                        pos.id,
                        option_symbol,
                        pos.quantity,
                    )
                    try:
                        await ntfy.notify_trade_skipped(
                            client,
                            settings,
                            alertsify_user_id=user_id,
                            position=pos,
                            tradier_option_symbol=option_symbol,
                            reason="no_premium",
                            chain_premium=chain_premium,
                        )
                    except Exception:
                        logger.exception(
                            "ntfy failed on no_premium skip user_id=%s alertsify_id=%s",
                            user_id,
                            pos.id,
                        )
                    continue
                if quantity < 1:
                    cost_per_contract = premium * sizing.OPTION_CONTRACT_MULTIPLIER
                    logger.warning(
                        "Skip open: order quantity below 1 "
                        "user_id=%s alertsify_id=%s option_symbol=%s "
                        "max_capital=%s premium=%s cost_per_contract=%s "
                        "alertsify_qty=%s capital_cap=%s",
                        user_id,
                        pos.id,
                        option_symbol,
                        settings.trade_max_capital,
                        premium,
                        cost_per_contract,
                        pos.quantity,
                        capital_cap,
                    )
                    try:
                        await ntfy.notify_trade_skipped(
                            client,
                            settings,
                            alertsify_user_id=user_id,
                            position=pos,
                            tradier_option_symbol=option_symbol,
                            reason="quantity_below_cap",
                            chain_premium=chain_premium,
                            drift=drift,
                            premium_per_share=premium,
                            capital_cap=capital_cap,
                            cost_per_contract=cost_per_contract,
                        )
                    except Exception:
                        logger.exception(
                            "ntfy failed on quantity_below_cap skip user_id=%s alertsify_id=%s",
                            user_id,
                            pos.id,
                        )
                    continue
                logger.info(
                    "Sized order qty=%s (alertsify_qty=%s capital_cap=%s) "
                    "max_capital=%s premium=%s user_id=%s alertsify_id=%s",
                    quantity,
                    pos.quantity,
                    capital_cap,
                    settings.trade_max_capital,
                    premium,
                    user_id,
                    pos.id,
                )

                preview = settings.tradier_preview_only
                try:
                    await ntfy.notify_trade_placing(
                        client,
                        settings,
                        alertsify_user_id=user_id,
                        position=pos,
                        tradier_option_symbol=option_symbol,
                        order_quantity=quantity,
                        premium_per_share=premium,
                        chain_premium=chain_premium,
                        drift=drift,
                        preview=preview,
                    )
                except Exception:
                    logger.exception(
                        "ntfy failed before placement user_id=%s alertsify_id=%s",
                        user_id,
                        pos.id,
                    )
                order_id = await tradier.place_option_order(
                    client,
                    settings,
                    underlying=pos.ticker,
                    option_symbol=option_symbol,
                    quantity=quantity,
                    preview=preview,
                )
                if preview:
                    logger.info(
                        "Preview only enabled; skipping DB persist "
                        "(user_id=%s alertsify_id=%s tradier_order_id=%s)",
                        user_id,
                        pos.id,
                        order_id,
                    )
                    continue

                await _run_in_thread(
                    partial(
                        db.record_placed_sync,
                        settings,
                        alertsify_user_id=user_id,
                        alertsify_position_id=pos.id,
                        alertsify_symbol=pos.symbol,
                        underlying=pos.ticker,
                        tradier_option_symbol=option_symbol,
                        tradier_order_id=order_id,
                        quantity=quantity,
                    ),
                )
                placed += 1
            except Exception:
                errors += 1
                logger.exception(
                    "Failed processing user_id=%s position id=%s",
                    user_id,
                    pos.id,
                )

    logger.info(
        "Poll cycle finished users=%d user_fetch_errors=%d positions=%d "
        "placed=%d closed=%d skipped_dup=%d skipped_drift=%d errors=%d",
        len(settings.alertsify_user_ids),
        user_fetch_errors,
        total_positions,
        placed,
        closed,
        skipped_dup,
        skipped_drift,
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
            if settings.poll_market_hours_only:
                now = datetime.now(ZoneInfo(settings.market_timezone))
                if not market_hours.is_us_weekday_session(
                    now,
                    tz_name=settings.market_timezone,
                    market_open=settings.market_open,
                    market_close=settings.market_close,
                ):
                    wait_s = market_hours.seconds_until_next_market_open(
                        now,
                        tz_name=settings.market_timezone,
                        market_open=settings.market_open,
                        market_close=settings.market_close,
                    )
                    eta = (now + timedelta(seconds=wait_s)).astimezone(
                        ZoneInfo(settings.market_timezone),
                    )
                    logger.info(
                        "Outside market session (%s %s-%s local); sleeping %.0fs "
                        "(next session start ~%s)",
                        settings.market_timezone,
                        settings.market_open.strftime("%H:%M"),
                        settings.market_close.strftime("%H:%M"),
                        wait_s,
                        eta.strftime("%Y-%m-%d %H:%M %Z"),
                    )
                    if await _sleep_until_or_stop(stop, wait_s):
                        break
                    continue

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
