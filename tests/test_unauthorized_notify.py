from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from alertsify_scraper.config import Settings
from alertsify_scraper.http_client import UnauthorizedNotifier, is_benign_401_response


def _settings(**overrides: object) -> Settings:
    base = {
        "alertsify_base_url": "https://alertsify.com",
        "alertsify_user_id_paper": "user_one",
        "libsql_url": "file:./test.db",
        "ntfy_base_url": "https://ntfy.sh",
        "ntfy_topic": "test-topic",
        "tradier_paper_api_key": "paper-key",
        "tradier_paper_account_id": "paper-acct",
    }
    base.update(overrides)
    return Settings(**base)


def test_benign_tradier_order_401() -> None:
    request = httpx.Request(
        "GET",
        "https://api.tradier.com/v1/accounts/ABC123/orders/999",
    )
    response = httpx.Response(401, request=request)
    assert is_benign_401_response(response) is True


def test_alertsify_401_not_benign() -> None:
    request = httpx.Request(
        "GET",
        "https://alertsify.com/api/snaptrade/option-positions?userId=u1",
    )
    response = httpx.Response(401, request=request)
    assert is_benign_401_response(response) is False


def test_tradier_orders_list_401_not_benign() -> None:
    request = httpx.Request(
        "GET",
        "https://api.tradier.com/v1/accounts/ABC123/orders",
    )
    response = httpx.Response(401, request=request)
    assert is_benign_401_response(response) is False


@pytest.mark.asyncio
async def test_unauthorized_notifier_rate_limits_to_one_per_hour() -> None:
    settings = _settings()
    notifier = UnauthorizedNotifier(cooldown=timedelta(hours=1))
    client = httpx.AsyncClient()
    notifier.bind_client(client)

    request = httpx.Request(
        "GET",
        "https://alertsify.com/api/snaptrade/option-positions?userId=u1",
    )
    response = httpx.Response(401, request=request)

    with patch(
        "alertsify_scraper.http_client.notify_http_unauthorized",
        new_callable=AsyncMock,
    ) as notify:
        await notifier.handle(settings, response)
        await notifier.handle(settings, response)

    notify.assert_awaited_once()
    await client.aclose()


@pytest.mark.asyncio
async def test_unauthorized_notifier_skips_benign_tradier_order_401() -> None:
    settings = _settings()
    notifier = UnauthorizedNotifier()
    client = httpx.AsyncClient()
    notifier.bind_client(client)

    request = httpx.Request(
        "GET",
        "https://api.tradier.com/v1/accounts/ABC123/orders/999",
    )
    response = httpx.Response(401, request=request)

    with patch(
        "alertsify_scraper.http_client.notify_http_unauthorized",
        new_callable=AsyncMock,
    ) as notify:
        await notifier.handle(settings, response)

    notify.assert_not_awaited()
    await client.aclose()


@pytest.mark.asyncio
async def test_unauthorized_notifier_respects_cooldown_expiry() -> None:
    settings = _settings()
    notifier = UnauthorizedNotifier(cooldown=timedelta(hours=1))
    client = httpx.AsyncClient()
    notifier.bind_client(client)
    notifier._last_notified_at = datetime.now(timezone.utc) - timedelta(hours=1, seconds=1)

    request = httpx.Request(
        "GET",
        "https://alertsify.com/api/snaptrade/option-positions?userId=u1",
    )
    response = httpx.Response(401, request=request)

    with patch(
        "alertsify_scraper.http_client.notify_http_unauthorized",
        new_callable=AsyncMock,
    ) as notify:
        await notifier.handle(settings, response)

    notify.assert_awaited_once()
    await client.aclose()
