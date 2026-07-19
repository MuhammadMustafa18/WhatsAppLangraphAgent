"""Auth controller — HTTP routes for register, login, refresh, me.

Thin layer: parse request → call service → return response.
No business logic here.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.db.models import User
from app.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


class MeResponse(BaseModel):
    """Minimal user info returned by GET /auth/me."""

    id: str
    username: str


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


@router.get("/me", response_model=MeResponse)
async def me(user: User = Depends(get_current_user)):
    """Return the currently authenticated user's id + username.

    Used by the Tauri UI's sidebar to render "Logged in as X".
    Requires a valid access token; 401 otherwise.
    """
    return MeResponse(id=user.id, username=user.username)
