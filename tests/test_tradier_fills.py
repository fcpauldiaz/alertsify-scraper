from alertsify_scraper.performance import (
    build_trade_performance,
    index_gainloss_by_symbol,
    index_positions_by_symbol,
)
from alertsify_scraper.tradier import order_fill_premium_per_share, position_entry_premium_per_share


def test_order_fill_premium_per_share_uses_avg_fill_price() -> None:
    assert order_fill_premium_per_share({"avg_fill_price": 2.15, "status": "filled"}) == 2.15


def test_order_fill_premium_per_share_ignores_unfilled() -> None:
    assert order_fill_premium_per_share({"avg_fill_price": 0.0, "status": "open"}) is None
    assert order_fill_premium_per_share({"avg_fill_price": 1.0, "status": "canceled"}) is None


def test_position_entry_premium_from_cost_basis() -> None:
    row = {"cost_basis": 430.0, "quantity": 2.0}
    assert position_entry_premium_per_share(row) == 2.15
