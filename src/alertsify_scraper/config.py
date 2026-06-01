from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

TRADIER_BASE_URL_PAPER = "https://sandbox.tradier.com"
TRADIER_BASE_URL_LIVE = "https://api.tradier.com"

TradingMode = Literal["paper", "live"]


@dataclass(frozen=True)
class TradierContext:
    mode: TradingMode
    api_base: str
    access_token: str
    account_id: str


def _parse_comma_ids(value: str) -> list[str]:
    parts = [p.strip() for p in value.split(",")]
    return [p for p in parts if p]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    alertsify_base_url: str = Field(..., min_length=1)
    alertsify_user_id_paper: str = Field(
        default="",
        validation_alias="ALERTSIFY_USER_ID_PAPER",
    )
    alertsify_user_id_live: str = Field(
        default="",
        validation_alias="ALERTSIFY_USER_ID_LIVE",
    )
    alertsify_user_id: str = Field(
        default="",
        validation_alias="ALERTSIFY_USER_ID",
    )
    alertsify_user_ids: list[str] = Field(default_factory=list)
    user_trading_modes: dict[str, TradingMode] = Field(default_factory=dict)
    using_legacy_user_config: bool = Field(default=False, exclude=True)
    alertsify_authorization: str | None = None
    alertsify_cookie: str | None = None
    alertsify_user_agent: str | None = None

    poll_interval_ms: int = Field(default=60_000, ge=1_000)
    poll_market_hours_only: bool = True
    market_timezone: str = Field(default="America/New_York", min_length=1)
    market_open: time = Field(default=time(9, 30))
    market_close: time = Field(default=time(16, 0))

    libsql_url: str = Field(..., min_length=1)
    libsql_auth_token: str = ""

    trading_mode: TradingMode = Field(default="paper")
    tradier_paper_api_key: str = ""
    tradier_live_api_key: str = ""
    tradier_paper_account_id: str = ""
    tradier_live_account_id: str = ""

    tradier_option_side: str = Field(default="buy_to_open")
    tradier_option_close_side: str = Field(default="sell_to_close")
    tradier_order_type: Literal["market", "limit"] = Field(default="market")
    tradier_order_duration: str = Field(default="day")
    tradier_limit_price: float | None = None
    tradier_preview_only: bool = False

    trade_max_capital: float = Field(default=2000.0, ge=1.0)

    ntfy_base_url: str = Field(default="https://ntfy.sh")
    ntfy_topic: str = Field(..., min_length=1)

    dashboard_host: str = Field(default="127.0.0.1")
    dashboard_port: int = Field(default=8080, ge=1, le=65535)
    dashboard_cors_origin: str = Field(default="http://127.0.0.1:5173")

    @model_validator(mode="after")
    def parse_alertsify_user_ids(self) -> Self:
        paper_ids = _parse_comma_ids(self.alertsify_user_id_paper)
        live_ids = _parse_comma_ids(self.alertsify_user_id_live)
        split_config = bool(paper_ids or live_ids)

        if split_config:
            legacy_ids = _parse_comma_ids(self.alertsify_user_id)
            if legacy_ids:
                msg = (
                    "Use ALERTSIFY_USER_ID_PAPER and ALERTSIFY_USER_ID_LIVE only; "
                    "do not set ALERTSIFY_USER_ID when split lists are configured"
                )
                raise ValueError(msg)
            if len(paper_ids) != len(set(paper_ids)):
                msg = "Duplicate Alertsify user id in ALERTSIFY_USER_ID_PAPER"
                raise ValueError(msg)
            if len(live_ids) != len(set(live_ids)):
                msg = "Duplicate Alertsify user id in ALERTSIFY_USER_ID_LIVE"
                raise ValueError(msg)
            modes: dict[str, TradingMode] = {}
            for uid in paper_ids:
                modes[uid] = "paper"
            for uid in live_ids:
                if uid in modes:
                    msg = f"Duplicate Alertsify user id across paper and live lists: {uid!r}"
                    raise ValueError(msg)
                modes[uid] = "live"
            all_ids = paper_ids + live_ids
            object.__setattr__(self, "using_legacy_user_config", False)
        else:
            legacy_ids = _parse_comma_ids(self.alertsify_user_id)
            if not legacy_ids:
                msg = (
                    "Configure ALERTSIFY_USER_ID_PAPER and/or ALERTSIFY_USER_ID_LIVE, "
                    "or legacy ALERTSIFY_USER_ID"
                )
                raise ValueError(msg)
            modes = {uid: self.trading_mode for uid in legacy_ids}
            all_ids = legacy_ids
            object.__setattr__(self, "using_legacy_user_config", True)

        object.__setattr__(self, "user_trading_modes", modes)
        object.__setattr__(self, "alertsify_user_ids", all_ids)
        return self

    def trading_mode_for_user(self, user_id: str) -> TradingMode:
        mode = self.user_trading_modes.get(user_id)
        if mode is None:
            msg = f"Unknown Alertsify user id: {user_id!r}"
            raise KeyError(msg)
        return mode

    def tradier_context_for_mode(self, mode: TradingMode) -> TradierContext:
        if mode == "paper":
            return TradierContext(
                mode="paper",
                api_base=TRADIER_BASE_URL_PAPER,
                access_token=self.tradier_paper_api_key,
                account_id=self.tradier_paper_account_id,
            )
        return TradierContext(
            mode="live",
            api_base=TRADIER_BASE_URL_LIVE,
            access_token=self.tradier_live_api_key,
            account_id=self.tradier_live_account_id,
        )

    def tradier_context_for_user(self, user_id: str) -> TradierContext:
        return self.tradier_context_for_mode(self.trading_mode_for_user(user_id))

    @field_validator("trading_mode", mode="before")
    @classmethod
    def normalize_trading_mode(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip().lower()
        return v

    @field_validator("market_timezone", mode="after")
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except ZoneInfoNotFoundError as exc:
            msg = "Invalid MARKET_TIMEZONE"
            raise ValueError(msg) from exc
        return v

    @field_validator("market_open", "market_close", mode="before")
    @classmethod
    def parse_hhmm_time(cls, v: object) -> object:
        if isinstance(v, time):
            return v
        if isinstance(v, str):
            parts = v.strip().split(":")
            if len(parts) != 2:
                msg = "Expected HH:MM"
                raise ValueError(msg)
            hour = int(parts[0])
            minute = int(parts[1])
            return time(hour, minute)
        return v

    @field_validator(
        "alertsify_authorization",
        "alertsify_cookie",
        "alertsify_user_agent",
        mode="before",
    )
    @classmethod
    def empty_optional_headers(cls, v: object) -> object:
        if isinstance(v, str):
            stripped = v.strip()
            return stripped or None
        return v

    @field_validator(
        "alertsify_base_url",
        "ntfy_base_url",
        mode="after",
    )
    @classmethod
    def strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")

    def model_post_init(self, __context: object) -> None:
        if self.market_open >= self.market_close:
            msg = "MARKET_OPEN must be before MARKET_CLOSE"
            raise ValueError(msg)
        if self.tradier_order_type == "limit" and self.tradier_limit_price is None:
            msg = "TRADIER_LIMIT_PRICE is required when TRADIER_ORDER_TYPE=limit"
            raise ValueError(msg)

        has_paper_users = any(m == "paper" for m in self.user_trading_modes.values())
        has_live_users = any(m == "live" for m in self.user_trading_modes.values())

        if has_paper_users:
            if not self.tradier_paper_api_key.strip():
                msg = "TRADIER_PAPER_API_KEY is required when paper Alertsify users are configured"
                raise ValueError(msg)
            if not self.tradier_paper_account_id.strip():
                msg = (
                    "TRADIER_PAPER_ACCOUNT_ID is required when paper Alertsify users are configured"
                )
                raise ValueError(msg)
        if has_live_users:
            if not self.tradier_live_api_key.strip():
                msg = "TRADIER_LIVE_API_KEY is required when live Alertsify users are configured"
                raise ValueError(msg)
            if not self.tradier_live_account_id.strip():
                msg = (
                    "TRADIER_LIVE_ACCOUNT_ID is required when live Alertsify users are configured"
                )
                raise ValueError(msg)
