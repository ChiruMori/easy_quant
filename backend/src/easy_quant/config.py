from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """运行配置；敏感值只从环境读取，禁止写入日志。"""

    model_config = SettingsConfigDict(
        env_prefix="EASY_QUANT_",
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: SecretStr = Field(description="MariaDB SQLAlchemy 连接 URL")
    secret_key: SecretStr = Field(default=SecretStr("development-only-change-me"))
    credential_encryption_key: SecretStr | None = None
    initial_admin_username: str = "admin"
    initial_admin_password: SecretStr = SecretStr("change-this-admin-password")
    session_cookie_secure: bool = False
    worker_poll_seconds: float = 1.0
    strategy_timeout_seconds: float = 30.0
    strategy_output_limit_bytes: int = 64 * 1024
    ntfy_base_url: str = "https://ntfy.sh"
    smtp_host: str | None = None
    smtp_port: int = 25
    smtp_sender: str | None = None
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    intraday_poll_seconds: int = 60
    intraday_run_time: str = "14:50"
    daily_data_publish_time: str = "22:00"

    @field_validator("intraday_run_time")
    @classmethod
    def trading_time(cls, value: str) -> str:
        from datetime import time

        parsed = time.fromisoformat(value)
        if parsed.tzinfo or not (
            time(9, 30) <= parsed <= time(11, 30) or time(13) <= parsed <= time(15)
        ):
            raise ValueError("盘中触发时间必须在交易时段内")
        return value

    @field_validator("intraday_run_time", "daily_data_publish_time")
    @classmethod
    def valid_time(cls, value: str) -> str:
        from datetime import time

        parsed = time.fromisoformat(value)
        if parsed.second or parsed.microsecond or parsed.tzinfo or len(value) != 5:
            raise ValueError("时间必须为 HH:MM")
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue] -- 必填值由 BaseSettings 从环境读取
