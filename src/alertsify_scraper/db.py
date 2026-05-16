from __future__ import annotations

import logging
from datetime import UTC, datetime

import libsql

from alertsify_scraper.config import Settings

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS placed_trades (
  alertsify_position_id TEXT PRIMARY KEY,
  alertsify_symbol TEXT NOT NULL,
  tradier_option_symbol TEXT NOT NULL,
  tradier_order_id TEXT NOT NULL,
  quantity INTEGER NOT NULL,
  created_at TEXT NOT NULL
);
"""


def _connect(settings: Settings):
    return libsql.connect(
        settings.libsql_url,
        auth_token=settings.libsql_auth_token or "",
    )


def migrate_sync(settings: Settings) -> None:
    conn = _connect(settings)
    try:
        conn.execute(SCHEMA_SQL)
        conn.commit()
        logger.info("libsql schema ensured at %s", settings.libsql_url)
    finally:
        conn.close()


def has_placed_sync(settings: Settings, position_id: str) -> bool:
    conn = _connect(settings)
    try:
        row = conn.execute(
            "SELECT 1 FROM placed_trades WHERE alertsify_position_id = ? LIMIT 1",
            (position_id,),
        ).fetchone()
        found = row is not None
        logger.debug("has_placed position_id=%s -> %s", position_id, found)
        return found
    finally:
        conn.close()


def record_placed_sync(
    settings: Settings,
    *,
    alertsify_position_id: str,
    alertsify_symbol: str,
    tradier_option_symbol: str,
    tradier_order_id: str,
    quantity: int,
) -> None:
    created_at = datetime.now(tz=UTC).isoformat()
    conn = _connect(settings)
    try:
        conn.execute(
            """
            INSERT INTO placed_trades (
              alertsify_position_id,
              alertsify_symbol,
              tradier_option_symbol,
              tradier_order_id,
              quantity,
              created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                alertsify_position_id,
                alertsify_symbol,
                tradier_option_symbol,
                tradier_order_id,
                quantity,
                created_at,
            ),
        )
        conn.commit()
        logger.info(
            "Recorded placed trade alertsify_id=%s tradier_order_id=%s",
            alertsify_position_id,
            tradier_order_id,
        )
    finally:
        conn.close()
