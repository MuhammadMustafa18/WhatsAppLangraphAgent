"""Auth DTOs — request/response models for authentication.

These define the HTTP contract. Separate from ORM models (app/db/models.py).
API layer reads/writes these. Service layer converts between DTOs and ORM.
"""

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, examples=["mustafa"])
    password: str = Field(..., min_length=6, max_length=100, examples=["secret123"])


class LoginRequest(BaseModel):
    username: str = Field(..., examples=["mustafa"])
    password: str = Field(..., examples=["secret123"])


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., examples=["eyJhbGciOiJIUzI1NiJ9..."])


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
