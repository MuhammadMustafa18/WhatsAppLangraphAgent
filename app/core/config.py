"""Typed application settings loaded from .env + environment variables.

Usage:
    from app.core.config import settings
    settings.OPENWA_API_KEY  # guaranteed str, not str | None
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration for the app. Required fields have no default —
    the app won't start if they're missing from .env or environment."""

    # --- Database ---
    DATABASE_URL: str = "sqlite+aiosqlite:///data/app.sqlite"

    # --- JWT (required) ---
    JWT_SECRET: str
    JWT_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_EXPIRE_DAYS: int = 7

    # --- Encryption (auto-generated on first boot if empty) ---
    ENCRYPTION_KEY: str = ""

    # --- OpenWA ---
    OPENWA_API_URL: str = "http://openwa:2785"
    OPENWA_API_KEY: str = ""
    OPENWA_SESSION_ID: str = "default"
    OPENWA_WEBHOOK_SECRET: str = ""

    # --- OpenAI / OpenAI-compatible ---
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "http://127.0.0.1:31415/v1"
    OPENAI_MODEL: str = "auto"

    # --- Anthropic ---
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_BASE_URL: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-4-5"

    # --- LangGraph ---
    CHECKPOINT_DB: str = "data/checkpoints.sqlite"

    # --- Logging ---
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton Settings instance. Cached so .env is read once at boot."""
    return Settings()
