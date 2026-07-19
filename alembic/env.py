"""Alembic env.py — configured for async SQLAlchemy.

Uses a sync engine for migrations (Alembic is synchronous internally).
This avoids conflicts with the app's running event loop.
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# Alembic Config object
config = context.config

# Logging setup
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import models so Alembic can detect them for autogenerate
from app.core.config import get_settings
from app.db.models import Base

target_metadata = Base.metadata

# Set sqlalchemy.url from our app settings (not hardcoded in alembic.ini).
# Alembic uses a SYNC engine, so we strip the "+aiosqlite" async driver
# suffix from the URL to avoid MissingGreenlet errors.
settings = get_settings()
url = settings.DATABASE_URL.replace("+aiosqlite", "")
# Resolve relative SQLite paths against APP_DATA_DIR (mirroring engine.py),
# falling back to the OS-conventional default so CLI alembic runs and the
# Tauri sidecar uvicorn process share one DB.
# Use the URL-style absolute path (4 slashes for sqlite://) so the sync
# engine opens the same file as the app's async engine.
if url.startswith("sqlite:///") and not url.startswith("sqlite:////"):
    from pathlib import Path
    from app.core.config import default_app_data_dir
    relative = url.replace("sqlite:///", "", 1)
    data_dir = (
        Path(settings.APP_DATA_DIR)
        if settings.APP_DATA_DIR
        else default_app_data_dir()
    )
    full = (data_dir / relative).resolve()
    full.parent.mkdir(parents=True, exist_ok=True)
    url = "sqlite://" + "/" + full.as_posix()
config.set_main_option("sqlalchemy.url", url)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — generates SQL without connecting."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode with sync engine.

    Alembic runs synchronously. Using a sync engine here avoids conflicts
    with the app's async event loop when called from lifespan.
    """
    import sys
    print(f"[env.py] creating sync engine (pid={__import__('os').getpid()})", flush=True)
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    print(f"[env.py] engine url: {connectable.url}", flush=True)
    with connectable.connect() as connection:
        print(f"[env.py] connected", flush=True)
        context.configure(connection=connection, target_metadata=target_metadata)
        print(f"[env.py] configured context", flush=True)
        with context.begin_transaction():
            print(f"[env.py] transaction begun", flush=True)
            context.run_migrations()
            print(f"[env.py] migrations done", flush=True)
    print(f"[env.py] done", flush=True)
    print(f"[env.py] disposing engine", flush=True)
    connectable.dispose()
    print(f"[env.py] disposed", flush=True)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
