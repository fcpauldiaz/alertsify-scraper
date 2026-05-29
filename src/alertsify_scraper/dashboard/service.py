from __future__ import annotations

import asyncio
from functools import partial
from typing import Any

import httpx

from alertsify_scraper import db, performance, tradier
from alertsify_scraper.config import Settings
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

    async def load_live_trades(
        self,
        client: httpx.AsyncClient,
        *,
        period: PeriodFilter = "all",
    ) -> tuple[list[performance.TradePerformance], performance.AccountBalancesView]:
        placed = await asyncio.to_thread(
            partial(db.list_live_trades_sync, self._settings),
        )
        balances_raw, positions, gainloss = await self._fetch_tradier_live(client)
        balances_view = performance.parse_balances_view(balances_raw)
        positions_by_symbol = performance.index_positions_by_symbol(positions)
        gainloss_by_symbol = performance.index_gainloss_by_symbol(gainloss)

        trade_rows = [
            performance.build_trade_performance(trade, positions_by_symbol, gainloss_by_symbol)
            for trade in placed
        ]
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
            balances_raw, positions, gainloss = await self._fetch_tradier_live(client)
            positions_by_symbol = performance.index_positions_by_symbol(positions)
            gainloss_by_symbol = performance.index_gainloss_by_symbol(gainloss)
            trades = [
                performance.build_trade_performance(t, positions_by_symbol, gainloss_by_symbol)
                for t in placed
            ]
            return performance.filter_trades_by_period(trades, period)
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
