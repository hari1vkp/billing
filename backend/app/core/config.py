from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    # App
    APP_NAME: str = "BillFlow"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    API_PREFIX: str = "/api/v1"

    # Database
    DATABASE_URL: str = (
        "postgresql+psycopg2://billing:billing_dev_pass@localhost:5433/billing"
    )

    # Security
    SECRET_KEY: str = "change-this-secret-key-in-production-please-1234567890"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ALGORITHM: str = "HS256"

    # Payment webhook verification (shared secret used to sign webhook payloads)
    PAYMENT_WEBHOOK_SECRET: str = "dev-webhook-secret-change-me"
    # Duration (minutes) after which an unpaid invoice is considered overdue (informational)
    INVOICE_DUE_GRACE_DAYS: int = 0

    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        # Tauri 2 desktop WebView origins — required so the packaged app can
        # call the FastAPI backend from the native WebView.
        "http://tauri.localhost",
        "tauri://localhost",
    ]

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS if o.strip()]


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
