from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

import libsql

from alertsify_scraper.config import Settings, TradingMode

logger = logging.getLogger(__name__)

STATUS_OPEN = "open"
STATUS_CLOSED = "closed"

SCHEMA_SQL = """
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
  created_at TEXT NOT NULL,
  closed_at TEXT,
  PRIMARY KEY (alertsify_user_id, alertsify_position_id)
);
"""

MIGRATION_LEGACY_COMPOSITE_SQL = """
CREATE TABLE placed_trades_new (
  alertsify_user_id TEXT NOT NULL DEFAULT '',
  alertsify_position_id TEXT NOT NULL,
  alertsify_symbol TEXT NOT NULL,
  tradier_option_symbol TEXT NOT NULL,
  tradier_order_id TEXT NOT NULL,
  quantity INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (alertsify_user_id, alertsify_position_id)
);

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
FROM placed_trades;

DROP TABLE placed_trades;

ALTER TABLE placed_trades_new RENAME TO placed_trades;
"""

MIGRATION_ADD_STATUS_COLUMNS = [
    "ALTER TABLE placed_trades ADD COLUMN underlying TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE placed_trades ADD COLUMN status TEXT NOT NULL DEFAULT 'open'",
    "ALTER TABLE placed_trades ADD COLUMN tradier_close_order_id TEXT",
    "ALTER TABLE placed_trades ADD COLUMN closed_at TEXT",
    "ALTER TABLE placed_trades ADD COLUMN trading_mode TEXT NOT NULL DEFAULT 'paper'",
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


def _connect(settings: Settings):
    return libsql.connect(
        settings.libsql_url,
        auth_token=settings.libsql_auth_token or "",
    )


def _table_columns(conn, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}


def migrate_sync(settings: Settings) -> None:
    conn = _connect(settings)
    try:
        conn.execute(SCHEMA_SQL)
        conn.commit()
        columns = _table_columns(conn, "placed_trades")
        if "alertsify_user_id" not in columns:
            logger.info("Migrating placed_trades to composite primary key")
            conn.executescript(MIGRATION_LEGACY_COMPOSITE_SQL)
            conn.commit()
            columns = _table_columns(conn, "placed_trades")
        for stmt in MIGRATION_ADD_STATUS_COLUMNS:
            col = stmt.split("ADD COLUMN ")[1].split()[0]
            if col not in columns:
                conn.execute(stmt)
                conn.commit()
                columns.add(col)
        logger.info("libsql schema ensured at %s", settings.libsql_url)
    finally:
        conn.close()


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
              created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(alertsify_user_id, alertsify_position_id) DO UPDATE SET
              alertsify_symbol = excluded.alertsify_symbol,
              underlying = excluded.underlying,
              tradier_option_symbol = excluded.tradier_option_symbol,
              tradier_order_id = excluded.tradier_order_id,
              quantity = excluded.quantity,
              trading_mode = excluded.trading_mode,
              status = excluded.status,
              tradier_close_order_id = NULL,
              closed_at = NULL,
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
) -> None:
    closed_at = datetime.now(tz=UTC).isoformat()
    conn = _connect(settings)
    try:
        conn.execute(
            """
            UPDATE placed_trades
            SET status = ?, tradier_close_order_id = ?, closed_at = ?
            WHERE alertsify_user_id = ? AND alertsify_position_id = ?
              AND status = ?
            """,
            (
                STATUS_CLOSED,
                tradier_close_order_id,
                closed_at,
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
