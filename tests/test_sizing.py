from alertsify_scraper.sizing import (
    MAX_ALERT_CHAIN_PREMIUM_DRIFT,
    drift_skip_reason,
)


def test_drift_skip_reason_paper_never_skips() -> None:
    assert drift_skip_reason("paper", None) is None
    assert drift_skip_reason("paper", 0.0) is None
    assert drift_skip_reason("paper", MAX_ALERT_CHAIN_PREMIUM_DRIFT + 1) is None


def test_drift_skip_reason_live_unavailable() -> None:
    assert drift_skip_reason("live", None) == "drift_unavailable"


def test_drift_skip_reason_live_within_limit() -> None:
    assert drift_skip_reason("live", MAX_ALERT_CHAIN_PREMIUM_DRIFT) is None
    assert drift_skip_reason("live", 0.05) is None


def test_drift_skip_reason_live_exceeded() -> None:
    assert drift_skip_reason("live", MAX_ALERT_CHAIN_PREMIUM_DRIFT + 0.01) == "drift_exceeded"
