from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    alertsify_base_url: str = Field(..., min_length=1)
    alertsify_user_id: str = Field(..., min_length=1)
    alertsify_authorization: str | None = None
    alertsify_cookie: str | None = None

    poll_interval_ms: int = Field(default=60_000, ge=1_000)

    libsql_url: str = Field(..., min_length=1)
    libsql_auth_token: str = ""

    tradier_api_base: str = Field(..., min_length=1)
    tradier_access_token: str = Field(..., min_length=1)
    tradier_account_id: str = Field(..., min_length=1)

    tradier_option_side: str = Field(default="buy_to_open")
    tradier_order_type: Literal["market", "limit"] = Field(default="market")
    tradier_order_duration: str = Field(default="day")
    tradier_limit_price: float | None = None
    tradier_preview_only: bool = False

    ntfy_base_url: str = Field(default="https://ntfy.sh")
    ntfy_topic: str = Field(..., min_length=1)

    @field_validator("alertsify_authorization", "alertsify_cookie", mode="before")
    @classmethod
    def empty_optional_headers(cls, v: object) -> object:
        if isinstance(v, str):
            stripped = v.strip()
            return stripped or None
        return v

    @field_validator(
        "alertsify_base_url",
        "tradier_api_base",
        "ntfy_base_url",
        mode="after",
    )
    @classmethod
    def strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")

    def model_post_init(self, __context: object) -> None:
        if self.tradier_order_type == "limit" and self.tradier_limit_price is None:
            msg = "TRADIER_LIMIT_PRICE is required when TRADIER_ORDER_TYPE=limit"
            raise ValueError(msg)
