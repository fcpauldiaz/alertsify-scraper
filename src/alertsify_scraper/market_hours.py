from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo


def is_us_weekday_session(
    now: datetime,
    *,
    tz_name: str,
    market_open: time,
    market_close: time,
) -> bool:
    local = now.astimezone(ZoneInfo(tz_name))
    if local.weekday() >= 5:
        return False
    t = local.time()
    return market_open <= t <= market_close


def seconds_until_next_market_open(
    now: datetime,
    *,
    tz_name: str,
    market_open: time,
    market_close: time,
) -> float:
    z = ZoneInfo(tz_name)
    local = now.astimezone(z)
    if local.weekday() < 5 and market_open <= local.time() <= market_close:
        return 0.0
    if local.weekday() < 5 and local.time() < market_open:
        nxt = datetime.combine(local.date(), market_open, z)
        return max(1.0, (nxt - local).total_seconds())

    d = local.date() + timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    nxt = datetime.combine(d, market_open, z)
    while nxt <= local:
        d += timedelta(days=1)
        while d.weekday() >= 5:
            d += timedelta(days=1)
        nxt = datetime.combine(d, market_open, z)
    return max(1.0, (nxt - local).total_seconds())
