"""Typed application settings loaded from .env + environment variables.

Usage:
    from app.core.config import settings
    settings.OPENWA_API_KEY  # guaranteed str, not str | None
"""

import secrets
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration for the app. Required fields have no default —
    the app won't start if they're missing from .env or environment."""

    # --- App (desktop mode) ---
    # %APPDATA% on Windows, ~/.local/share on Linux, ~/Library/Application
    # Support on macOS. Per-user, per-app data lives here. The Tauri sidecar
    # also sets this env var so the FastAPI process opens the same DB.
    # Override APP_DATA_DIR in .env only for non-desktop runs (tests, CI).
    APP_DATA_DIR: str = ""
    API_PORT: int = 18234
    API_HOST: str = "127.0.0.1"

    # --- Database ---
    # APP_DATA_DIR is the directory that holds runtime data. DATABASE_URL
    # points at a file *inside* that directory — not a subdir like
    # "data/app.sqlite", which would double up with APP_DATA_DIR.
    DATABASE_URL: str = "sqlite+aiosqlite:///app.sqlite"

    # --- JWT ---
    # Empty string means "not yet generated".  On first boot the app
    # generates a random secret and persists it to .env so tokens stay
    # valid across restarts.
    JWT_SECRET: str = ""
    JWT_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_EXPIRE_DAYS: int = 7

    # --- Encryption (auto-generated on first boot if empty) ---
    ENCRYPTION_KEY: str = ""

    # --- Baileys sidecar ---
    # Local HTTP API of the Baileys WhatsApp gateway sidecar.
    # Tauri spawns this process automatically; no Docker needed.
    BAILEYS_SIDECAR_URL: str = "http://127.0.0.1:2786"

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
    LOG_FORMAT: str = "dev"  # "dev" for pretty console, "json" for production

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


def ensure_jwt_secret() -> str:
    """Return JWT_SECRET, generating + persisting one if it was empty.

    In dev mode the secret comes from .env at the project root. In a
    bundled Tauri exe the .env is unreachable (PyInstaller temp dir /
    wrong CWD), so Settings() sees the empty default. This function
    generates a random 64-char hex string, writes it to .env in the
    resolved APP_DATA_DIR, and clears the Settings cache so subsequent
    get_settings() calls pick it up.
    """
    settings = get_settings()
    if settings.JWT_SECRET:
        return settings.JWT_SECRET

    new_secret = secrets.token_hex(32)
    _persist_env_var("JWT_SECRET", new_secret)
    get_settings.cache_clear()
    return new_secret


def _persist_env_var(key: str, value: str) -> None:
    """Write KEY=VALUE to .env in the data dir (or CWD), updating in-place."""
    settings = get_settings()
    if settings.APP_DATA_DIR:
        env_path = Path(settings.APP_DATA_DIR) / ".env"
    else:
        env_path = Path(".env")

    env_path.parent.mkdir(parents=True, exist_ok=True)
    line = f"{key}={value}"

    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
        replaced = False
        for i, ln in enumerate(lines):
            if ln.strip().startswith(f"{key}="):
                lines[i] = line
                replaced = True
                break
        if not replaced:
            lines.append(line)
        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    else:
        env_path.write_text(line + "\n", encoding="utf-8")


def default_app_data_dir() -> Path:
    """Per-user, per-app data directory, OS-aware.

    Includes a 'data/' subdirectory because DATABASE_URL points at
    `app.sqlite` (no path prefix). Tests / CLI / sidecar all share
    this directory so they see the same SQLite file.

    Windows: %APPDATA%\\com.recluze.desktop\\data
    macOS:   ~/Library/Application Support/com.recluze.desktop/data
    Linux:   $XDG_DATA_HOME/com.recluze.desktop/data or
             ~/.local/share/com.recluze.desktop/data
    """
    import os
    import sys

    app_name = "com.recluze.desktop"
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / app_name / "data"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / app_name / "data"
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / app_name / "data"
