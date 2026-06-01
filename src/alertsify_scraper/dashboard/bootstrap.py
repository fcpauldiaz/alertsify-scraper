from __future__ import annotations

import json

from alertsify_scraper.config import Settings


def inject_dashboard_bootstrap(html: str, settings: Settings) -> str:
    api_key = settings.dashboard_api_key.strip()
    config = {
        "apiKey": api_key or None,
        "authRequired": bool(api_key),
    }
    script = f"<script>window.__ALERTSIFY_DASHBOARD__={json.dumps(config)};</script>"
    if "</head>" in html:
        return html.replace("</head>", f"{script}</head>", 1)
    return f"{script}{html}"
