from __future__ import annotations

import asyncio
from functools import partial
from typing import Any

import httpx

from alertsify_scraper import db, performance, tradier
from alertsify_scraper.config import Settings
from alertsify_scraper.db import PlacedTrade
from alertsify_scraper.performance import PeriodFilter


class DashboardService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _has_live_credentials(self) -> bool:
        return bool(
            self._settings.tradier_live_api_key.strip()
            and self._settings.tradier_live_account_id.strip()
        )

    async def _fetch_tradier_live(
        self,
        client: httpx.AsyncClient,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
        if not self._has_live_credentials():
            return {}, [], []
        ctx = self._settings.tradier_context_for_mode("live")
        balances, positions, gainloss = await asyncio.gather(
            tradier.fetch_account_balances(client, ctx),
            tradier.fetch_account_positions(client, ctx),
            tradier.fetch_account_gainloss(client, ctx),
        )
        return balances, positions, gainloss

    def _order_ids_for_trades(self, trades: list[PlacedTrade]) -> set[str]:
        order_ids: set[str] = set()
        for trade in trades:
            if trade.tradier_order_id:
                order_ids.add(trade.tradier_order_id)
            if trade.tradier_close_order_id:
                order_ids.add(trade.tradier_close_order_id)
        return order_ids

    async def _fetch_broker_orders(
        self,
        client: httpx.AsyncClient,
        trades: list[PlacedTrade],
    ) -> dict[str, dict[str, Any]]:
        if not self._has_live_credentials():
            return {}
        ctx = self._settings.tradier_context_for_mode("live")
        return await tradier.fetch_orders_by_id(
            client,
            ctx,
            self._order_ids_for_trades(trades),
        )

    async def _build_trade_rows(
        self,
        client: httpx.AsyncClient,
        placed: list[PlacedTrade],
    ) -> tuple[list[performance.TradePerformance], performance.AccountBalancesView]:
        balances_raw, positions, gainloss = await self._fetch_tradier_live(client)
        orders_by_id = await self._fetch_broker_orders(client, placed)
        balances_view = performance.parse_balances_view(balances_raw)
        positions_by_symbol = performance.index_positions_by_symbol(positions)
        gainloss_by_symbol = performance.index_gainloss_by_symbol(gainloss)
        trade_rows = [
            performance.build_trade_performance(
                trade,
                positions_by_symbol,
                gainloss_by_symbol,
                orders_by_id,
            )
            for trade in placed
        ]
        return trade_rows, balances_view

    async def load_live_trades(
        self,
        client: httpx.AsyncClient,
        *,
        period: PeriodFilter = "all",
    ) -> tuple[list[performance.TradePerformance], performance.AccountBalancesView]:
        placed = await asyncio.to_thread(
            partial(db.list_live_trades_sync, self._settings),
        )
        trade_rows, balances_view = await self._build_trade_rows(client, placed)
        return performance.filter_trades_by_period(trade_rows, period), balances_view

    async def get_summary(
        self,
        client: httpx.AsyncClient,
        *,
        period: PeriodFilter = "all",
    ) -> performance.PortfolioSummary:
        trades, balances = await self.load_live_trades(client, period=period)
        return performance.build_portfolio_summary(trades, balances)

    async def get_trades(
        self,
        client: httpx.AsyncClient,
        *,
        period: PeriodFilter = "all",
        status: str | None = None,
        limit: int = 500,
    ) -> list[performance.TradePerformance]:
        if status is not None:
            placed = await asyncio.to_thread(
                partial(
                    db.list_live_trades_sync,
                    self._settings,
                    status=status,
                    limit=limit,
                ),
            )
            trade_rows, _ = await self._build_trade_rows(client, placed)
            return performance.filter_trades_by_period(trade_rows, period)
        trades, _ = await self.load_live_trades(client, period=period)
        return trades[:limit]

    async def get_equity_curve(
        self,
        client: httpx.AsyncClient,
        *,
        period: PeriodFilter = "all",
    ) -> list[performance.EquityCurvePoint]:
        trades, _ = await self.load_live_trades(client, period="all")
        return performance.build_equity_curve(trades, period=period)

    def live_configured(self) -> bool:
        return self._has_live_credentials()
