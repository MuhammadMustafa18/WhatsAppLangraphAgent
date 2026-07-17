"""Auth service — business logic for register, login, refresh.

No HTTP, no DB queries, no password hashing details.
Just orchestration: validate → hash → create → return tokens.
"""

from fastapi import HTTPException, status

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.repositories import user_repo
from app.schemas.auth import TokenResponse
from sqlalchemy.ext.asyncio import AsyncSession


async def register(db: AsyncSession, username: str, password: str) -> TokenResponse:
    """Register a new user. Returns token pair."""
    # Check if username is taken
    existing = await user_repo.get_user_by_username(db, username)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already taken",
        )

    # Create user (hash password first)
    hashed = hash_password(password)
    user = await user_repo.create_user(db, username, hashed)

    # Return tokens
    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


async def login(db: AsyncSession, username: str, password: str) -> TokenResponse:
    """Login with credentials. Returns token pair."""
    user = await user_repo.get_user_by_username(db, username)
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


async def refresh(refresh_token: str) -> TokenResponse:
    """Exchange a refresh token for a new access token."""
    payload = decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    user_id = payload["sub"]
    return TokenResponse(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
    )
