"""FastAPI dependency injection.

get_db() yields an async SQLAlchemy session per request.
Usage:
    @app.get("/something")
    async def handler(db: AsyncSession = Depends(get_db)):
        ...
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import async_session


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session
