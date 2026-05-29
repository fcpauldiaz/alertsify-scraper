from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from alertsify_scraper.db import PlacedTrade, STATUS_CLOSED, STATUS_OPEN
from alertsify_scraper.sizing import OPTION_CONTRACT_MULTIPLIER

PeriodFilter = Literal["all", "7d", "30d"]


@dataclass(frozen=True)
class AccountBalancesView:
    total_equity: float | None
    total_cash: float | None
    buying_power: float | None
    market_value: float | None


@dataclass(frozen=True)
class TradePerformance:
    alertsify_user_id: str
    alertsify_position_id: str
    alertsify_symbol: str
    underlying: str
    tradier_option_symbol: str
    quantity: int
    status: str
    entry_premium_per_share: float | None
    current_or_exit_premium_per_share: float | None
    unrealized_pnl: float | None
    realized_pnl: float | None
    pnl_percent: float | None
    notional_at_entry: float | None
    hold_duration_seconds: float | None
    created_at: str
    closed_at: str | None


@dataclass(frozen=True)
class PortfolioSummary:
    total_equity: float | None
    buying_power: float | None
    total_unrealized_pnl: float
    total_realized_pnl: float
    open_count: int
    closed_count: int
    win_rate: float | None
    avg_winner: float | None
    avg_loser: float | None
    pnl_by_underlying: dict[str, float]


@dataclass(frozen=True)
class EquityCurvePoint:
    date: str
    cumulative_realized_pnl: float


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _period_cutoff(period: PeriodFilter) -> datetime | None:
    now = datetime.now(tz=UTC)
    if period == "7d":
        return now - timedelta(days=7)
    if period == "30d":
        return now - timedelta(days=30)
    return None


def _trade_in_period(trade: PlacedTrade, period: PeriodFilter) -> bool:
    cutoff = _period_cutoff(period)
    if cutoff is None:
        return True
    if trade.status == STATUS_OPEN:
        opened = _parse_iso(trade.created_at)
        return opened is not None and opened >= cutoff
    closed = _parse_iso(trade.closed_at)
    return closed is not None and closed >= cutoff


def _float_field(row: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = row.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def parse_balances_view(balances: dict[str, Any]) -> AccountBalancesView:
    return AccountBalancesView(
        total_equity=_float_field(balances, "total_equity", "equity"),
        total_cash=_float_field(balances, "total_cash", "cash"),
        buying_power=_float_field(balances, "option_buying_power", "buying_power"),
        market_value=_float_field(balances, "market_value"),
    )


def index_positions_by_symbol(
    positions: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in positions:
        symbol = row.get("symbol")
        if isinstance(symbol, str) and symbol:
            indexed[symbol] = row
    return indexed


def index_gainloss_by_symbol(
    closed_positions: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in closed_positions:
        symbol = row.get("symbol")
        if isinstance(symbol, str) and symbol:
            indexed[symbol] = row
    return indexed


def _position_mark_premium(row: dict[str, Any]) -> float | None:
    return _float_field(row, "last", "close", "average_cost")


def _gainloss_realized(row: dict[str, Any]) -> float | None:
    return _float_field(row, "gain_loss", "gainloss", "realized_gain_loss")


def _notional(quantity: int, premium_per_share: float | None) -> float | None:
    if premium_per_share is None:
        return None
    return quantity * premium_per_share * OPTION_CONTRACT_MULTIPLIER


def _pnl_percent(pnl: float | None, notional: float | None) -> float | None:
    if pnl is None or notional is None or notional == 0:
        return None
    return (pnl / notional) * 100.0


def _hold_duration_seconds(trade: PlacedTrade) -> float | None:
    opened = _parse_iso(trade.created_at)
    if opened is None:
        return None
    end = _parse_iso(trade.closed_at) if trade.status == STATUS_CLOSED else datetime.now(tz=UTC)
    if end is None:
        return None
    return max(0.0, (end - opened).total_seconds())


def _computed_realized_pnl(
    trade: PlacedTrade,
    gainloss_row: dict[str, Any] | None,
) -> float | None:
    if trade.realized_pnl is not None:
        return trade.realized_pnl
    if gainloss_row is not None:
        gl = _gainloss_realized(gainloss_row)
        if gl is not None:
            return gl
    entry = trade.entry_premium_per_share
    exit_p = trade.exit_premium_per_share
    if entry is not None and exit_p is not None:
        return (exit_p - entry) * trade.quantity * OPTION_CONTRACT_MULTIPLIER
    return None


def _computed_unrealized_pnl(
    trade: PlacedTrade,
    position_row: dict[str, Any] | None,
) -> float | None:
    entry = trade.entry_premium_per_share
    if entry is None:
        return None
    current: float | None = None
    if position_row is not None:
        current = _position_mark_premium(position_row)
        cost = _float_field(position_row, "cost_basis", "average_cost")
        gl = _float_field(position_row, "gain_loss", "gainloss")
        if gl is not None:
            return gl
        if cost is not None and current is not None:
            qty_mult = trade.quantity * OPTION_CONTRACT_MULTIPLIER
            return (current - entry) * qty_mult
    if current is not None:
        return (current - entry) * trade.quantity * OPTION_CONTRACT_MULTIPLIER
    return None


def build_trade_performance(
    trade: PlacedTrade,
    positions_by_symbol: dict[str, dict[str, Any]],
    gainloss_by_symbol: dict[str, dict[str, Any]],
) -> TradePerformance:
    position_row = positions_by_symbol.get(trade.tradier_option_symbol)
    gainloss_row = gainloss_by_symbol.get(trade.tradier_option_symbol)

    realized = _computed_realized_pnl(trade, gainloss_row) if trade.status == STATUS_CLOSED else None
    unrealized = (
        _computed_unrealized_pnl(trade, position_row) if trade.status == STATUS_OPEN else None
    )

    current_or_exit: float | None = None
    if trade.status == STATUS_OPEN and position_row is not None:
        current_or_exit = _position_mark_premium(position_row)
    elif trade.exit_premium_per_share is not None:
        current_or_exit = trade.exit_premium_per_share

    notional = _notional(trade.quantity, trade.entry_premium_per_share)
    active_pnl = unrealized if trade.status == STATUS_OPEN else realized

    return TradePerformance(
        alertsify_user_id=trade.alertsify_user_id,
        alertsify_position_id=trade.alertsify_position_id,
        alertsify_symbol=trade.alertsify_symbol,
        underlying=trade.underlying,
        tradier_option_symbol=trade.tradier_option_symbol,
        quantity=trade.quantity,
        status=trade.status,
        entry_premium_per_share=trade.entry_premium_per_share,
        current_or_exit_premium_per_share=current_or_exit,
        unrealized_pnl=unrealized,
        realized_pnl=realized,
        pnl_percent=_pnl_percent(active_pnl, notional),
        notional_at_entry=notional,
        hold_duration_seconds=_hold_duration_seconds(trade),
        created_at=trade.created_at,
        closed_at=trade.closed_at,
    )


def build_portfolio_summary(
    trades: list[TradePerformance],
    balances: AccountBalancesView,
) -> PortfolioSummary:
    open_trades = [t for t in trades if t.status == STATUS_OPEN]
    closed_trades = [t for t in trades if t.status == STATUS_CLOSED]

    total_unrealized = sum(t.unrealized_pnl or 0.0 for t in open_trades)
    closed_with_pnl = [t for t in closed_trades if t.realized_pnl is not None]
    total_realized = sum(t.realized_pnl or 0.0 for t in closed_with_pnl)

    winners = [t.realized_pnl for t in closed_with_pnl if (t.realized_pnl or 0) > 0]
    losers = [t.realized_pnl for t in closed_with_pnl if (t.realized_pnl or 0) < 0]

    win_rate: float | None = None
    if closed_with_pnl:
        win_rate = len(winners) / len(closed_with_pnl)

    pnl_by_underlying: dict[str, float] = {}
    for trade in trades:
        key = trade.underlying or "unknown"
        pnl = trade.unrealized_pnl if trade.status == STATUS_OPEN else trade.realized_pnl
        if pnl is not None:
            pnl_by_underlying[key] = pnl_by_underlying.get(key, 0.0) + pnl

    return PortfolioSummary(
        total_equity=balances.total_equity,
        buying_power=balances.buying_power,
        total_unrealized_pnl=total_unrealized,
        total_realized_pnl=total_realized,
        open_count=len(open_trades),
        closed_count=len(closed_trades),
        win_rate=win_rate,
        avg_winner=(sum(winners) / len(winners)) if winners else None,
        avg_loser=(sum(losers) / len(losers)) if losers else None,
        pnl_by_underlying=pnl_by_underlying,
    )


def build_equity_curve(
    trades: list[TradePerformance],
    period: PeriodFilter = "all",
) -> list[EquityCurvePoint]:
    closed = [
        t
        for t in trades
        if t.status == STATUS_CLOSED and t.realized_pnl is not None and t.closed_at
    ]
    cutoff = _period_cutoff(period)
    if cutoff is not None:
        filtered: list[TradePerformance] = []
        for trade in closed:
            closed_at = _parse_iso(trade.closed_at)
            if closed_at is not None and closed_at >= cutoff:
                filtered.append(trade)
        closed = filtered

    closed.sort(key=lambda t: t.closed_at or "")
    cumulative = 0.0
    by_date: dict[str, float] = {}
    for trade in closed:
        cumulative += trade.realized_pnl or 0.0
        day = (trade.closed_at or "")[:10]
        if day:
            by_date[day] = cumulative

    return [
        EquityCurvePoint(date=day, cumulative_realized_pnl=pnl)
        for day, pnl in sorted(by_date.items())
    ]


def filter_trades_by_period(
    trades: list[TradePerformance],
    period: PeriodFilter,
) -> list[TradePerformance]:
    if period == "all":
        return trades
    return [
        TradePerformance(
            alertsify_user_id=t.alertsify_user_id,
            alertsify_position_id=t.alertsify_position_id,
            alertsify_symbol=t.alertsify_symbol,
            underlying=t.underlying,
            tradier_option_symbol=t.tradier_option_symbol,
            quantity=t.quantity,
            status=t.status,
            entry_premium_per_share=t.entry_premium_per_share,
            current_or_exit_premium_per_share=t.current_or_exit_premium_per_share,
            unrealized_pnl=t.unrealized_pnl,
            realized_pnl=t.realized_pnl,
            pnl_percent=t.pnl_percent,
            notional_at_entry=t.notional_at_entry,
            hold_duration_seconds=t.hold_duration_seconds,
            created_at=t.created_at,
            closed_at=t.closed_at,
        )
        for t in trades
        if _trade_in_period(
            PlacedTrade(
                alertsify_user_id=t.alertsify_user_id,
                alertsify_position_id=t.alertsify_position_id,
                alertsify_symbol=t.alertsify_symbol,
                underlying=t.underlying,
                tradier_option_symbol=t.tradier_option_symbol,
                tradier_order_id="",
                tradier_close_order_id=None,
                quantity=t.quantity,
                trading_mode="live",
                status=t.status,
                entry_premium_per_share=t.entry_premium_per_share,
                exit_premium_per_share=None,
                realized_pnl=t.realized_pnl,
                created_at=t.created_at,
                closed_at=t.closed_at,
            ),
            period,
        )
    ]
