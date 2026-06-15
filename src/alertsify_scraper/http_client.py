from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import httpx

from alertsify_scraper.config import Settings
from alertsify_scraper.ntfy import notify_http_unauthorized

logger = logging.getLogger(__name__)

_TRADIER_ORDER_401 = re.compile(
    r"/v1/accounts/[^/]+/orders/[^/?#]+$",
    re.IGNORECASE,
)

_UNAUTHORIZED_NOTIFY_COOLDOWN = timedelta(hours=1)


def is_benign_401_response(response: httpx.Response) -> bool:
    if response.status_code != 401:
        return False
    request = response.request
    if request.method.upper() != "GET":
        return False
    path = request.url.path
    return bool(_TRADIER_ORDER_401.search(path))


def _host_from_url(url: str) -> str:
    return urlparse(url).netloc.lower()


def _is_ntfy_request(settings: Settings, response: httpx.Response) -> bool:
    host = (response.request.url.host or "").lower()
    ntfy_host = _host_from_url(settings.ntfy_base_url)
    return bool(host) and host == ntfy_host


def _infer_source(settings: Settings, response: httpx.Response) -> str:
    host = (response.request.url.host or "").lower()
    alertsify_host = _host_from_url(settings.alertsify_base_url)
    if host == alertsify_host:
        return "Alertsify"
    if host == _host_from_url("https://sandbox.tradier.com"):
        return "Tradier (paper)"
    if host == _host_from_url("https://api.tradier.com"):
        return "Tradier (live)"
    return host or "unknown"


class UnauthorizedNotifier:
    def __init__(self, *, cooldown: timedelta = _UNAUTHORIZED_NOTIFY_COOLDOWN) -> None:
        self._cooldown = cooldown
        self._last_notified_at: datetime | None = None
        self._client: httpx.AsyncClient | None = None

    def bind_client(self, client: httpx.AsyncClient) -> None:
        self._client = client

    def response_hook(self, settings: Settings):
        async def on_response(response: httpx.Response) -> None:
            await self.handle(settings, response)

        return on_response

    async def handle(self, settings: Settings, response: httpx.Response) -> None:
        if response.status_code != 401:
            return
        if is_benign_401_response(response):
            return
        if _is_ntfy_request(settings, response):
            return
        if self._client is None:
            logger.warning(
                "401 on %s but HTTP client is not bound for ntfy notification",
                response.request.url,
            )
            return

        now = datetime.now(timezone.utc)
        if self._last_notified_at is not None:
            elapsed = now - self._last_notified_at
            if elapsed < self._cooldown:
                logger.debug(
                    "401 on %s suppressed (notified %.0fs ago, cooldown %.0fs)",
                    response.request.url,
                    elapsed.total_seconds(),
                    self._cooldown.total_seconds(),
                )
                return

        self._last_notified_at = now
        request = response.request
        source = _infer_source(settings, response)
        try:
            await notify_http_unauthorized(
                self._client,
                settings,
                source=source,
                method=request.method.upper(),
                url=str(request.url),
            )
        except Exception:
            logger.exception("Failed sending 401 ntfy notification for %s", request.url)


def create_http_client(settings: Settings, *, timeout: float = 60.0) -> httpx.AsyncClient:
    notifier = UnauthorizedNotifier()
    client = httpx.AsyncClient(
        timeout=httpx.Timeout(timeout),
        event_hooks={"response": [notifier.response_hook(settings)]},
    )
    notifier.bind_client(client)
    return client
