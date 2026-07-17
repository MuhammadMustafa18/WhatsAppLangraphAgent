"""User repository — all DB queries for the users table.

No business logic, no HTTP, no password hashing.
Just pure SQLAlchemy queries. This is the only place that touches User rows.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User


async def get_user_by_id(db: AsyncSession, user_id: str) -> User | None:
    """Look up a user by UUID."""
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_user_by_username(db: AsyncSession, username: str) -> User | None:
    """Look up a user by username (for login)."""
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def create_user(db: AsyncSession, username: str, password_hash: str) -> User:
    """Insert a new user. Commits immediately."""
    user = User(username=username, password_hash=password_hash)
    db.add(user)
    await db.commit()
    await db.refresh(user)  # reload to get auto-generated id + created_at
    return user
