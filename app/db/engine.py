"""Async SQLAlchemy engine + session factory for SQLite.

Usage in dependencies:
    from app.db.engine import async_session
    async with async_session() as session:
        ...
"""

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import default_app_data_dir, get_settings

settings = get_settings()


def _resolve_db_url() -> str:
    """Resolve DATABASE_URL relative to APP_DATA_DIR if it's a relative path.

    APP_DATA_DIR falls back to the OS-conventional per-user app data
    directory when unset, so the desktop app and CLI runs share the same DB.

    The resolved path is converted to a URL-style absolute path (forward
    slashes, with an extra leading slash on non-Windows or a leading
    "/C:/" on Windows) so SQLAlchemy's URL parser handles it correctly
    for BOTH the async engine and the sync engine used by alembic.

    Bug history: previously we formatted as `sqlite:///C:\\Users\\...`
    (3 slashes). SQLAlchemy parsed `.database` as the relative filename
    "C:\\Users\\...app.sqlite", so alembic (sync engine) opened a
    different file than the app (async engine) — alembic saw an empty
    DB and tried to re-run all migrations, hanging on the SQLite file
    lock. Fix: emit `sqlite:////C:/Users/...` (4 slashes) so the path
    is unambiguously absolute.
    """
    db_url = settings.DATABASE_URL
    if db_url.startswith("sqlite+aiosqlite:///") and not db_url.startswith("sqlite+aiosqlite:////"):
        relative_path = db_url.replace("sqlite+aiosqlite:///", "")
        data_dir = (
            Path(settings.APP_DATA_DIR)
            if settings.APP_DATA_DIR
            else default_app_data_dir()
        )
        full_path = (data_dir / relative_path).resolve()
        full_path.parent.mkdir(parents=True, exist_ok=True)
        # Convert WindowsPath "C:\Users\..." to URL-style "/C:/Users/...".
        # as_posix() gives forward slashes; we prepend "/" so the URL
        # has 4 slashes total (3 from sqlite+aiosqlite:// + 1 absolute).
        url_path = "/" + full_path.as_posix()
        return f"sqlite+aiosqlite://{url_path}"
    return db_url


engine = create_async_engine(
    _resolve_db_url(),
    echo=False,
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
