from __future__ import annotations

from typing import Any

from alertsify_scraper.performance import (
    EquityCurvePoint,
    PortfolioSummary,
    TradePerformance,
)


def trade_to_dict(trade: TradePerformance) -> dict[str, Any]:
    return {
        "alertsify_user_id": trade.alertsify_user_id,
        "alertsify_position_id": trade.alertsify_position_id,
        "alertsify_symbol": trade.alertsify_symbol,
        "underlying": trade.underlying,
        "tradier_option_symbol": trade.tradier_option_symbol,
        "quantity": trade.quantity,
        "status": trade.status,
        "entry_premium_per_share": trade.entry_premium_per_share,
        "current_or_exit_premium_per_share": trade.current_or_exit_premium_per_share,
        "unrealized_pnl": trade.unrealized_pnl,
        "realized_pnl": trade.realized_pnl,
        "pnl_percent": trade.pnl_percent,
        "notional_at_entry": trade.notional_at_entry,
        "hold_duration_seconds": trade.hold_duration_seconds,
        "created_at": trade.created_at,
        "closed_at": trade.closed_at,
    }


def summary_to_dict(summary: PortfolioSummary) -> dict[str, Any]:
    return {
        "total_equity": summary.total_equity,
        "buying_power": summary.buying_power,
        "total_unrealized_pnl": summary.total_unrealized_pnl,
        "total_realized_pnl": summary.total_realized_pnl,
        "open_count": summary.open_count,
        "closed_count": summary.closed_count,
        "win_rate": summary.win_rate,
        "avg_winner": summary.avg_winner,
        "avg_loser": summary.avg_loser,
        "pnl_by_underlying": summary.pnl_by_underlying,
    }


def equity_point_to_dict(point: EquityCurvePoint) -> dict[str, Any]:
    return {
        "date": point.date,
        "cumulative_realized_pnl": point.cumulative_realized_pnl,
    }
