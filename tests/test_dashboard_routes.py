from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from alertsify_scraper.config import Settings
from alertsify_scraper.dashboard.app import create_app


def _settings() -> Settings:
    return Settings(
        alertsify_base_url="https://alertsify.com",
        alertsify_user_id_paper="user_one",
        libsql_url="file::memory:?cache=shared",
        ntfy_base_url="https://ntfy.sh",
        ntfy_topic="test-topic",
    )


@pytest.fixture
def dashboard_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (assets / "app.js").write_text("console.log('ok');", encoding="utf-8")
    (dist / "index.html").write_text("<html><body>dashboard</body></html>", encoding="utf-8")
    monkeypatch.setenv("DASHBOARD_DIST_DIR", str(dist))
    return TestClient(create_app(_settings()))


def test_dashboard_root_serves_index(dashboard_client: TestClient) -> None:
    response = dashboard_client.get("/")
    assert response.status_code == 200
    assert "dashboard" in response.text


def test_unknown_routes_return_404(dashboard_client: TestClient) -> None:
    for path in ("/.env", "/metrics", "/wp/wp-includes/wlwmanifest.xml", "/missing"):
        response = dashboard_client.get(path)
        assert response.status_code == 404, path
