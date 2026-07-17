"""Quick check: list all tables in the database."""

import asyncio
from sqlalchemy import text
from app.db.engine import async_session


async def main():
    async with async_session() as session:
        result = await session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table'")
        )
        tables = [row[0] for row in result.fetchall()]
        print("Tables:", tables)

        # Also describe the users table
        result = await session.execute(text("PRAGMA table_info(users)"))
        columns = [(row[1], row[2]) for row in result.fetchall()]
        print("Users columns:", columns)


asyncio.run(main())
