from pathlib import Path

from alertsify_scraper.dashboard.app import resolve_dashboard_dist


def test_resolve_dashboard_dist_finds_built_ui() -> None:
    dist = resolve_dashboard_dist()
    assert (dist / "index.html").is_file()
    assets = dist / "assets"
    assert assets.is_dir()
    assert any(Path(p).suffix == ".js" for p in assets.iterdir())
