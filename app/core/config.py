from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_env: str = "development"
    app_base_url: str = "http://localhost:8000"
    log_level: str = "INFO"
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/mailforge"
    admin_api_token: str = "change-me-in-production"
    unsubscribe_signing_secret: str = "change-me-in-production"
    sendgrid_api_key: str = ""
    sendgrid_from_email: str = ""
    sendgrid_from_name: str = ""
    sendgrid_webhook_verification_key: str = ""
    sendgrid_unsubscribe_group_id: int | None = None
    worker_stale_timeout_seconds: int = 300
    max_send_attempts: int = 5
    default_send_rate_per_hour: int = 1000
    max_csv_bytes: int = 10_000_000
    max_csv_rows: int = 100_000
    max_metadata_bytes: int = 8_192
    webhook_signature_required: bool = True
    sql_echo: bool = False
    cors_origins: list[str] = Field(default_factory=list)

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+asyncpg://", 1)
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        return value

    @field_validator("sendgrid_unsubscribe_group_id", mode="before")
    @classmethod
    def empty_unsubscribe_group_is_none(cls, value: object) -> object:
        return None if value == "" else value


@lru_cache
def get_settings() -> Settings:
    return Settings()
