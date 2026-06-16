from alertsify_scraper.alertsify import OptionPosition
from alertsify_scraper.config import Settings
from alertsify_scraper.sizing import (
    MAX_ALERT_CHAIN_PREMIUM_DRIFT,
    contracts_for_min_capital,
    contracts_from_capital,
    drift_skip_reason,
    estimated_order_cost,
    resolve_open_quantity,
)


def _settings(**overrides: object) -> Settings:
    base = {
        "alertsify_base_url": "https://alertsify.com",
        "ALERTSIFY_USER_ID_PAPER": "user_one",
        "libsql_url": "file:./test.db",
        "ntfy_base_url": "https://ntfy.sh",
        "ntfy_topic": "test-topic",
        "tradier_paper_api_key": "paper-key",
        "tradier_paper_account_id": "paper-acct",
        "trade_max_capital": 2000.0,
        "trade_min_capital": 1000.0,
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)


def _position(*, quantity: int = 1, entry_price: float = 8.0) -> OptionPosition:
    return OptionPosition(
        id="pos-1",
        symbol="AAPL240119C00150000",
        ticker="AAPL",
        strike=150.0,
        side="buy",
        expirationLabel="Jan 19",
        expirationDate="2024-01-19",
        quantity=quantity,
        entryPrice=entry_price,
        currentPrice=entry_price,
        pnl=0.0,
        optionType="call",
        isBroadcast=False,
    )


def _chain(option_symbol: str, ask: float) -> list[dict[str, object]]:
    return [{"symbol": option_symbol, "ask": ask}]


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


def test_estimated_order_cost() -> None:
    assert estimated_order_cost(2, 5.0) == 1000.0
    assert estimated_order_cost(1, 8.0) == 800.0


def test_contracts_for_min_capital() -> None:
    assert contracts_for_min_capital(1000.0, 8.0) == 2
    assert contracts_for_min_capital(1000.0, 15.0) == 1
    assert contracts_for_min_capital(1000.0, 5.0) == 2


def test_contracts_from_capital() -> None:
    assert contracts_from_capital(2000.0, 8.0) == 2
    assert contracts_from_capital(2000.0, 25.0) == 0


def test_resolve_open_quantity_scales_up_for_min_capital() -> None:
    settings = _settings()
    option_symbol = "AAPL240119C00150000"
    chain = _chain(option_symbol, 8.0)
    position = _position(quantity=1)

    quantity, premium, capital_cap, min_qty = resolve_open_quantity(
        settings,
        chain,
        option_symbol,
        position,
    )

    assert premium == 8.0
    assert capital_cap == 2
    assert min_qty == 2
    assert quantity == 2
    assert estimated_order_cost(quantity, premium) == 1600.0


def test_resolve_open_quantity_already_meets_min() -> None:
    settings = _settings()
    option_symbol = "AAPL240119C00150000"
    chain = _chain(option_symbol, 15.0)
    position = _position(quantity=1)

    quantity, premium, capital_cap, min_qty = resolve_open_quantity(
        settings,
        chain,
        option_symbol,
        position,
    )

    assert premium == 15.0
    assert capital_cap == 1
    assert min_qty == 1
    assert quantity == 1


def test_resolve_open_quantity_cap_binds_above_min() -> None:
    settings = _settings()
    option_symbol = "AAPL240119C00150000"
    chain = _chain(option_symbol, 8.0)
    position = _position(quantity=3)

    quantity, premium, capital_cap, min_qty = resolve_open_quantity(
        settings,
        chain,
        option_symbol,
        position,
    )

    assert capital_cap == 2
    assert min_qty == 2
    assert quantity == 2


def test_resolve_open_quantity_exact_floor() -> None:
    settings = _settings()
    option_symbol = "AAPL240119C00150000"
    chain = _chain(option_symbol, 5.0)
    position = _position(quantity=1)

    quantity, premium, capital_cap, min_qty = resolve_open_quantity(
        settings,
        chain,
        option_symbol,
        position,
    )

    assert capital_cap == 4
    assert min_qty == 2
    assert quantity == 2
    assert estimated_order_cost(quantity, premium) == 1000.0


def test_resolve_open_quantity_unmet_min_capital() -> None:
    settings = _settings()
    option_symbol = "AAPL240119C00150000"
    chain = _chain(option_symbol, 25.0)
    position = _position(quantity=1)

    quantity, premium, capital_cap, min_qty = resolve_open_quantity(
        settings,
        chain,
        option_symbol,
        position,
    )

    assert premium == 25.0
    assert capital_cap == 0
    assert min_qty == 1
    assert quantity == 0
