from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

import libsql

from alertsify_scraper.config import Settings, TradingMode

logger = logging.getLogger(__name__)

STATUS_OPEN = "open"
STATUS_CLOSED = "closed"
LIVE_MODE: TradingMode = "live"

SCHEMA_STATEMENTS = [
    """
CREATE TABLE IF NOT EXISTS placed_trades (
  alertsify_user_id TEXT NOT NULL DEFAULT '',
  alertsify_position_id TEXT NOT NULL,
  alertsify_symbol TEXT NOT NULL,
  underlying TEXT NOT NULL DEFAULT '',
  tradier_option_symbol TEXT NOT NULL,
  tradier_order_id TEXT NOT NULL,
  quantity INTEGER NOT NULL,
  trading_mode TEXT NOT NULL DEFAULT 'paper',
  status TEXT NOT NULL DEFAULT 'open',
  tradier_close_order_id TEXT,
  entry_premium_per_share REAL,
  exit_premium_per_share REAL,
  realized_pnl REAL,
  created_at TEXT NOT NULL,
  closed_at TEXT,
  PRIMARY KEY (alertsify_user_id, alertsify_position_id)
)
""",
    """
CREATE TABLE IF NOT EXISTS open_skips (
  alertsify_user_id TEXT NOT NULL,
  alertsify_position_id TEXT NOT NULL,
  skip_reason TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (alertsify_user_id, alertsify_position_id)
)
""",
]

MIGRATION_LEGACY_COMPOSITE_STATEMENTS = [
    """
CREATE TABLE placed_trades_new (
  alertsify_user_id TEXT NOT NULL DEFAULT '',
  alertsify_position_id TEXT NOT NULL,
  alertsify_symbol TEXT NOT NULL,
  tradier_option_symbol TEXT NOT NULL,
  tradier_order_id TEXT NOT NULL,
  quantity INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (alertsify_user_id, alertsify_position_id)
)
""",
    """
INSERT INTO placed_trades_new (
  alertsify_user_id,
  alertsify_position_id,
  alertsify_symbol,
  tradier_option_symbol,
  tradier_order_id,
  quantity,
  created_at
)
SELECT
  '',
  alertsify_position_id,
  alertsify_symbol,
  tradier_option_symbol,
  tradier_order_id,
  quantity,
  created_at
FROM placed_trades
""",
    "DROP TABLE placed_trades",
    "ALTER TABLE placed_trades_new RENAME TO placed_trades",
]

MIGRATION_ADD_STATUS_COLUMNS = [
    "ALTER TABLE placed_trades ADD COLUMN underlying TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE placed_trades ADD COLUMN status TEXT NOT NULL DEFAULT 'open'",
    "ALTER TABLE placed_trades ADD COLUMN tradier_close_order_id TEXT",
    "ALTER TABLE placed_trades ADD COLUMN closed_at TEXT",
    "ALTER TABLE placed_trades ADD COLUMN trading_mode TEXT NOT NULL DEFAULT 'paper'",
]

MIGRATION_ADD_PREMIUM_COLUMNS = [
    "ALTER TABLE placed_trades ADD COLUMN entry_premium_per_share REAL",
    "ALTER TABLE placed_trades ADD COLUMN exit_premium_per_share REAL",
    "ALTER TABLE placed_trades ADD COLUMN realized_pnl REAL",
]


@dataclass(frozen=True)
class OpenTrade:
    alertsify_user_id: str
    alertsify_position_id: str
    alertsify_symbol: str
    underlying: str
    tradier_option_symbol: str
    quantity: int
    trading_mode: TradingMode


@dataclass(frozen=True)
class PlacedTrade:
    alertsify_user_id: str
    alertsify_position_id: str
    alertsify_symbol: str
    underlying: str
    tradier_option_symbol: str
    tradier_order_id: str
    tradier_close_order_id: str | None
    quantity: int
    trading_mode: TradingMode
    status: str
    entry_premium_per_share: float | None
    exit_premium_per_share: float | None
    realized_pnl: float | None
    created_at: str
    closed_at: str | None


@dataclass(frozen=True)
class LiveTradeSummary:
    total_trades: int
    open_count: int
    closed_count: int
    distinct_underlyings: int


def _connect(settings: Settings):
    return libsql.connect(
        settings.libsql_url,
        auth_token=settings.libsql_auth_token or "",
    )


def _table_columns(conn, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}


def _execute_each(conn, statements: list[str]) -> None:
    for stmt in statements:
        conn.execute(stmt)
    conn.commit()


def _row_to_placed_trade(row: tuple) -> PlacedTrade:
    return PlacedTrade(
        alertsify_user_id=row[0],
        alertsify_position_id=row[1],
        alertsify_symbol=row[2],
        underlying=row[3],
        tradier_option_symbol=row[4],
        tradier_order_id=row[5],
        tradier_close_order_id=row[6],
        quantity=row[7],
        trading_mode=row[8],
        status=row[9],
        entry_premium_per_share=row[10],
        exit_premium_per_share=row[11],
        realized_pnl=row[12],
        created_at=row[13],
        closed_at=row[14],
    )


_PLACED_TRADE_SELECT = """
SELECT
  alertsify_user_id,
  alertsify_position_id,
  alertsify_symbol,
  underlying,
  tradier_option_symbol,
  tradier_order_id,
  tradier_close_order_id,
  quantity,
  trading_mode,
  status,
  entry_premium_per_share,
  exit_premium_per_share,
  realized_pnl,
  created_at,
  closed_at
FROM placed_trades
"""


def migrate_sync(settings: Settings) -> None:
    conn = _connect(settings)
    try:
        _execute_each(conn, SCHEMA_STATEMENTS)
        columns = _table_columns(conn, "placed_trades")
        if "alertsify_user_id" not in columns:
            logger.info("Migrating placed_trades to composite primary key")
            _execute_each(conn, MIGRATION_LEGACY_COMPOSITE_STATEMENTS)
            columns = _table_columns(conn, "placed_trades")
        for stmt in MIGRATION_ADD_STATUS_COLUMNS:
            col = stmt.split("ADD COLUMN ")[1].split()[0]
            if col not in columns:
                conn.execute(stmt)
                conn.commit()
                columns.add(col)
        for stmt in MIGRATION_ADD_PREMIUM_COLUMNS:
            col = stmt.split("ADD COLUMN ")[1].split()[0]
            if col not in columns:
                conn.execute(stmt)
                conn.commit()
                columns.add(col)
        logger.info("libsql schema ensured at %s", settings.libsql_url)
    finally:
        conn.close()


def has_open_skip_sync(
    settings: Settings,
    alertsify_user_id: str,
    position_id: str,
) -> bool:
    conn = _connect(settings)
    try:
        row = conn.execute(
            """
            SELECT 1 FROM open_skips
            WHERE alertsify_user_id = ? AND alertsify_position_id = ?
            LIMIT 1
            """,
            (alertsify_user_id, position_id),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def record_open_skip_sync(
    settings: Settings,
    *,
    alertsify_user_id: str,
    alertsify_position_id: str,
    skip_reason: str,
) -> None:
    created_at = datetime.now(tz=UTC).isoformat()
    conn = _connect(settings)
    try:
        conn.execute(
            """
            INSERT INTO open_skips (
              alertsify_user_id,
              alertsify_position_id,
              skip_reason,
              created_at
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(alertsify_user_id, alertsify_position_id) DO NOTHING
            """,
            (alertsify_user_id, alertsify_position_id, skip_reason, created_at),
        )
        conn.commit()
        logger.info(
            "Recorded open skip user_id=%s alertsify_id=%s reason=%s",
            alertsify_user_id,
            alertsify_position_id,
            skip_reason,
        )
    finally:
        conn.close()


def is_open_position_handled_sync(
    settings: Settings,
    alertsify_user_id: str,
    position_id: str,
) -> bool:
    return has_open_placed_sync(
        settings,
        alertsify_user_id,
        position_id,
    ) or has_open_skip_sync(settings, alertsify_user_id, position_id)


def has_open_placed_sync(
    settings: Settings,
    alertsify_user_id: str,
    position_id: str,
) -> bool:
    conn = _connect(settings)
    try:
        row = conn.execute(
            """
            SELECT 1 FROM placed_trades
            WHERE alertsify_user_id = ? AND alertsify_position_id = ?
              AND status = ?
            LIMIT 1
            """,
            (alertsify_user_id, position_id, STATUS_OPEN),
        ).fetchone()
        found = row is not None
        logger.debug(
            "has_open_placed user_id=%s position_id=%s -> %s",
            alertsify_user_id,
            position_id,
            found,
        )
        return found
    finally:
        conn.close()


def list_open_trades_sync(
    settings: Settings,
    alertsify_user_id: str,
) -> list[OpenTrade]:
    conn = _connect(settings)
    try:
        rows = conn.execute(
            """
            SELECT
              alertsify_user_id,
              alertsify_position_id,
              alertsify_symbol,
              underlying,
              tradier_option_symbol,
              quantity,
              trading_mode
            FROM placed_trades
            WHERE alertsify_user_id = ? AND status = ?
            """,
            (alertsify_user_id, STATUS_OPEN),
        ).fetchall()
        return [
            OpenTrade(
                alertsify_user_id=row[0],
                alertsify_position_id=row[1],
                alertsify_symbol=row[2],
                underlying=row[3],
                tradier_option_symbol=row[4],
                quantity=row[5],
                trading_mode=row[6],
            )
            for row in rows
        ]
    finally:
        conn.close()


def list_live_trades_sync(
    settings: Settings,
    *,
    status: str | None = None,
    limit: int | None = None,
    since: str | None = None,
) -> list[PlacedTrade]:
    clauses = ["trading_mode = ?"]
    params: list[object] = [LIVE_MODE]
    if status is not None:
        clauses.append("status = ?")
        params.append(status)
    if since is not None:
        clauses.append("created_at >= ?")
        params.append(since)
    where = " AND ".join(clauses)
    sql = f"{_PLACED_TRADE_SELECT} WHERE {where} ORDER BY created_at DESC"
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    conn = _connect(settings)
    try:
        rows = conn.execute(sql, tuple(params)).fetchall()
        return [_row_to_placed_trade(row) for row in rows]
    finally:
        conn.close()


def live_trade_summary_sync(settings: Settings) -> LiveTradeSummary:
    conn = _connect(settings)
    try:
        row = conn.execute(
            """
            SELECT
              COUNT(*) AS total,
              SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) AS open_count,
              SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) AS closed_count,
              COUNT(DISTINCT underlying) AS distinct_underlyings
            FROM placed_trades
            WHERE trading_mode = ?
            """,
            (STATUS_OPEN, STATUS_CLOSED, LIVE_MODE),
        ).fetchone()
        return LiveTradeSummary(
            total_trades=int(row[0] or 0),
            open_count=int(row[1] or 0),
            closed_count=int(row[2] or 0),
            distinct_underlyings=int(row[3] or 0),
        )
    finally:
        conn.close()


def update_trade_realized_pnl_sync(
    settings: Settings,
    *,
    alertsify_user_id: str,
    alertsify_position_id: str,
    realized_pnl: float,
    exit_premium_per_share: float | None = None,
) -> None:
    conn = _connect(settings)
    try:
        if exit_premium_per_share is not None:
            conn.execute(
                """
                UPDATE placed_trades
                SET realized_pnl = ?, exit_premium_per_share = ?
                WHERE alertsify_user_id = ? AND alertsify_position_id = ?
                  AND trading_mode = ?
                """,
                (
                    realized_pnl,
                    exit_premium_per_share,
                    alertsify_user_id,
                    alertsify_position_id,
                    LIVE_MODE,
                ),
            )
        else:
            conn.execute(
                """
                UPDATE placed_trades
                SET realized_pnl = ?
                WHERE alertsify_user_id = ? AND alertsify_position_id = ?
                  AND trading_mode = ?
                """,
                (
                    realized_pnl,
                    alertsify_user_id,
                    alertsify_position_id,
                    LIVE_MODE,
                ),
            )
        conn.commit()
    finally:
        conn.close()


def record_placed_sync(
    settings: Settings,
    *,
    alertsify_user_id: str,
    alertsify_position_id: str,
    alertsify_symbol: str,
    underlying: str,
    tradier_option_symbol: str,
    tradier_order_id: str,
    quantity: int,
    trading_mode: TradingMode,
    entry_premium_per_share: float | None = None,
) -> None:
    created_at = datetime.now(tz=UTC).isoformat()
    conn = _connect(settings)
    try:
        conn.execute(
            """
            INSERT INTO placed_trades (
              alertsify_user_id,
              alertsify_position_id,
              alertsify_symbol,
              underlying,
              tradier_option_symbol,
              tradier_order_id,
              quantity,
              trading_mode,
              status,
              entry_premium_per_share,
              created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(alertsify_user_id, alertsify_position_id) DO UPDATE SET
              alertsify_symbol = excluded.alertsify_symbol,
              underlying = excluded.underlying,
              tradier_option_symbol = excluded.tradier_option_symbol,
              tradier_order_id = excluded.tradier_order_id,
              quantity = excluded.quantity,
              trading_mode = excluded.trading_mode,
              status = excluded.status,
              entry_premium_per_share = excluded.entry_premium_per_share,
              tradier_close_order_id = NULL,
              closed_at = NULL,
              exit_premium_per_share = NULL,
              realized_pnl = NULL,
              created_at = excluded.created_at
            """,
            (
                alertsify_user_id,
                alertsify_position_id,
                alertsify_symbol,
                underlying,
                tradier_option_symbol,
                tradier_order_id,
                quantity,
                trading_mode,
                STATUS_OPEN,
                entry_premium_per_share,
                created_at,
            ),
        )
        conn.commit()
        logger.info(
            "Recorded open trade user_id=%s alertsify_id=%s tradier_order_id=%s",
            alertsify_user_id,
            alertsify_position_id,
            tradier_order_id,
        )
    finally:
        conn.close()


def mark_closed_sync(
    settings: Settings,
    *,
    alertsify_user_id: str,
    alertsify_position_id: str,
    tradier_close_order_id: str,
    exit_premium_per_share: float | None = None,
) -> None:
    closed_at = datetime.now(tz=UTC).isoformat()
    conn = _connect(settings)
    try:
        conn.execute(
            """
            UPDATE placed_trades
            SET status = ?, tradier_close_order_id = ?, closed_at = ?,
                exit_premium_per_share = COALESCE(?, exit_premium_per_share)
            WHERE alertsify_user_id = ? AND alertsify_position_id = ?
              AND status = ?
            """,
            (
                STATUS_CLOSED,
                tradier_close_order_id,
                closed_at,
                exit_premium_per_share,
                alertsify_user_id,
                alertsify_position_id,
                STATUS_OPEN,
            ),
        )
        conn.commit()
        logger.info(
            "Marked trade closed user_id=%s alertsify_id=%s close_order_id=%s",
            alertsify_user_id,
            alertsify_position_id,
            tradier_close_order_id,
        )
    finally:
        conn.close()
