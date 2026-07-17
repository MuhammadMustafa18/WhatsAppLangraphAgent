"""Auth controller — HTTP routes for register, login, refresh.

Thin layer: parse request → call service → return response.
No business logic here.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse)
async def register(data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register a new user. Returns access + refresh tokens."""
    return await auth_service.register(db, data.username, data.password)


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Login with username + password. Returns access + refresh tokens."""
    return await auth_service.login(db, data.username, data.password)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(data: RefreshRequest):
    """Exchange a refresh token for a new token pair."""
    return await auth_service.refresh(data.refresh_token)
