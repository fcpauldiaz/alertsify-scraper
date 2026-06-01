from alertsify_scraper.config import Settings
from alertsify_scraper.dashboard.bootstrap import inject_dashboard_bootstrap


def test_inject_dashboard_bootstrap_adds_api_key() -> None:
    settings = Settings.model_construct(
        dashboard_api_key="secret-key",
    )
    html = "<html><head></head><body></body></html>"
    result = inject_dashboard_bootstrap(html, settings)
    assert "__ALERTSIFY_DASHBOARD__" in result
    assert "secret-key" in result
    assert '"authRequired": true' in result


def test_inject_dashboard_bootstrap_without_key() -> None:
    settings = Settings.model_construct(
        dashboard_api_key="",
    )
    html = "<html><head></head><body></body></html>"
    result = inject_dashboard_bootstrap(html, settings)
    assert '"authRequired": false' in result
