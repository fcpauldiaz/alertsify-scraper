from alertsify_scraper.alertsify import OptionPositionsResponse


def _valid_position(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": "pos-1",
        "symbol": "AAPL Jan 19 180C",
        "ticker": "AAPL",
        "strike": 180.0,
        "side": "long",
        "expirationLabel": "Jan 19",
        "expirationDate": "2026-01-19",
        "quantity": 1,
        "entryPrice": 210,
        "currentPrice": 250,
        "pnl": 40.0,
        "optionType": "call",
        "isBroadcast": True,
    }
    base.update(overrides)
    return base


def test_from_api_payload_accepts_null_mark_and_pnl() -> None:
    parsed = OptionPositionsResponse.from_api_payload(
        {
            "success": True,
            "total": 1,
            "positions": [
                _valid_position(
                    id="sim-ptsjrnsu",
                    currentPrice=None,
                    pnl=None,
                    isBroadcast=False,
                ),
            ],
        }
    )

    assert parsed.success is True
    assert len(parsed.positions) == 1
    assert parsed.positions[0].id == "sim-ptsjrnsu"
    assert parsed.positions[0].current_price is None
    assert parsed.positions[0].pnl is None


def test_from_api_payload_skips_positions_missing_required_fields() -> None:
    parsed = OptionPositionsResponse.from_api_payload(
        {
            "success": True,
            "total": 2,
            "positions": [
                _valid_position(id="pos-good"),
                {"id": "pos-bad"},
                _valid_position(id="pos-good-2"),
            ],
        }
    )

    assert parsed.success is True
    assert parsed.total == 2
    assert [p.id for p in parsed.positions] == ["pos-good", "pos-good-2"]


def test_from_api_payload_keeps_valid_positions_when_all_good() -> None:
    parsed = OptionPositionsResponse.from_api_payload(
        {
            "success": True,
            "total": 1,
            "positions": [_valid_position()],
        }
    )

    assert len(parsed.positions) == 1
    assert parsed.positions[0].entry_price == 2.1
