from __future__ import annotations

from alertsify_scraper.db import PlacedTrade
from alertsify_scraper.performance import (
    build_equity_curve,
    build_portfolio_summary,
    build_trade_performance,
    index_gainloss_by_symbol,
    index_positions_by_symbol,
    parse_balances_view,
)


def _trade(
    *,
    status: str = "closed",
    symbol: str = "AAPL240119C00180000",
    entry: float | None = 2.1,
    exit_p: float | None = 2.5,
    realized: float | None = None,
    closed_at: str | None = "2024-01-20T16:00:00+00:00",
) -> PlacedTrade:
    return PlacedTrade(
        alertsify_user_id="user-live",
        alertsify_position_id="pos-1",
        alertsify_symbol="AAPL Jan 19 180C",
        underlying="AAPL",
        tradier_option_symbol=symbol,
        tradier_order_id="open-1",
        tradier_close_order_id="close-1" if status == "closed" else None,
        quantity=2,
        trading_mode="live",
        status=status,
        entry_premium_per_share=entry,
        exit_premium_per_share=exit_p,
        realized_pnl=realized,
        created_at="2024-01-15T15:00:00+00:00",
        closed_at=closed_at if status == "closed" else None,
    )


def test_build_trade_performance_uses_gainloss_for_closed() -> None:
    trade = _trade(realized=None)
    gainloss = {
        "symbol": trade.tradier_option_symbol,
        "gain_loss": 120.0,
    }
    perf = build_trade_performance(
        trade,
        index_positions_by_symbol([]),
        index_gainloss_by_symbol([gainloss]),
    )
    assert perf.realized_pnl == 120.0
    assert perf.unrealized_pnl is None


def test_build_trade_performance_prefers_order_fill_for_entry() -> None:
    trade = _trade(status="open", entry=2.0, exit_p=None, closed_at=None)
    orders = {"open-1": {"avg_fill_price": 2.15, "status": "filled"}}
    perf = build_trade_performance(trade, {}, {}, orders_by_id=orders)
    assert perf.entry_premium_per_share == 2.15


def test_build_trade_performance_realized_from_order_fills() -> None:
    trade = _trade(realized=None, entry=99.0, exit_p=99.0)
    orders = {
        "open-1": {"avg_fill_price": 2.0, "status": "filled"},
        "close-1": {"avg_fill_price": 2.5, "status": "filled"},
    }
    perf = build_trade_performance(trade, {}, {}, orders_by_id=orders)
    assert perf.realized_pnl == (2.5 - 2.0) * 2 * 100
    assert perf.entry_premium_per_share == 2.0
    assert perf.current_or_exit_premium_per_share == 2.5


def test_build_trade_performance_gainloss_overrides_fill_pnl() -> None:
    trade = _trade(realized=None)
    gainloss = {
        "symbol": trade.tradier_option_symbol,
        "gain_loss": 120.0,
    }
    orders = {
        "open-1": {"avg_fill_price": 2.0, "status": "filled"},
        "close-1": {"avg_fill_price": 2.3, "status": "filled"},
    }
    perf = build_trade_performance(
        trade,
        {},
        index_gainloss_by_symbol([gainloss]),
        orders_by_id=orders,
    )
    assert perf.realized_pnl == 120.0


def test_build_trade_performance_computes_unrealized_from_position() -> None:
    trade = _trade(status="open", exit_p=None, closed_at=None)
    positions = [
        {
            "symbol": trade.tradier_option_symbol,
            "last": 2.4,
            "gain_loss": 60.0,
        },
    ]
    perf = build_trade_performance(
        trade,
        index_positions_by_symbol(positions),
        index_gainloss_by_symbol([]),
    )
    assert perf.unrealized_pnl == 60.0
    assert perf.realized_pnl is None


def test_build_trade_performance_fallback_realized_from_premiums() -> None:
    trade = _trade(realized=None, exit_p=2.5, entry=2.0)
    perf = build_trade_performance(trade, {}, {})
    assert perf.realized_pnl == (2.5 - 2.0) * 2 * 100


def test_portfolio_summary_win_rate() -> None:
    trades = [
        build_trade_performance(
            _trade(realized=100.0, symbol="SYM1"),
            {},
            {"SYM1": {"symbol": "SYM1", "gain_loss": 100.0}},
        ),
        build_trade_performance(
            _trade(realized=-50.0, symbol="SYM2"),
            {},
            {"SYM2": {"symbol": "SYM2", "gain_loss": -50.0}},
        ),
    ]
    balances = parse_balances_view({"total_equity": 50000})
    summary = build_portfolio_summary(trades, balances)
    assert summary.total_realized_pnl == 50.0
    assert summary.win_rate == 0.5
    assert summary.total_equity == 50000.0


def test_equity_curve_cumulative_by_day() -> None:
    trades = [
        build_trade_performance(
            _trade(realized=100.0, closed_at="2024-01-10T16:00:00+00:00", symbol="A"),
            {},
            {"A": {"symbol": "A", "gain_loss": 100.0}},
        ),
        build_trade_performance(
            _trade(realized=50.0, closed_at="2024-01-12T16:00:00+00:00", symbol="B"),
            {},
            {"B": {"symbol": "B", "gain_loss": 50.0}},
        ),
    ]
    curve = build_equity_curve(trades, period="all")
    assert len(curve) == 2
    assert curve[0].cumulative_realized_pnl == 100.0
    assert curve[1].cumulative_realized_pnl == 150.0
