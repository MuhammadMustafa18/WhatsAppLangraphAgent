"""Async SQLAlchemy engine + session factory for SQLite.

Usage in dependencies:
    from app.db.engine import async_session
    async with async_session() as session:
        ...
"""

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()


def _resolve_db_url() -> str:
    """Resolve DATABASE_URL relative to APP_DATA_DIR if it's a relative path."""
    db_url = settings.DATABASE_URL
    if db_url.startswith("sqlite+aiosqlite:///") and not db_url.startswith("sqlite+aiosqlite:////"):
        # Relative path — resolve against APP_DATA_DIR
        relative_path = db_url.replace("sqlite+aiosqlite:///", "")
        data_dir = Path(settings.APP_DATA_DIR)
        full_path = (data_dir / relative_path).resolve()
        full_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite+aiosqlite:///{full_path}"
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
