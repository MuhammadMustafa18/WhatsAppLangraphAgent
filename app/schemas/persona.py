"""Persona DTOs — request/response shapes for /personas endpoints.

HTTP contract. Separate from the ORM model (app/db/models.py Persona)
because:
  - id/user_id/created_at are server-managed, never accepted from clients.
  - Validation rules (system_prompt min length, knowledge_base max) belong
    at the wire boundary, not on the ORM model.
  - model_override is exposed as a plain UUID — the FK lookup happens in
    the service layer (Phase 20), not here.

The service layer is responsible for converting these to/from ORM rows.
Repos don't see DTOs.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class PersonaCreate(BaseModel):
    """Body for POST /personas."""

    name: str = Field(..., min_length=1, max_length=100, examples=["support-bot"])
    system_prompt: str = Field(..., min_length=1, examples=["You are a helpful assistant."])
    knowledge_base: str | None = Field(
        default=None,
        description="Optional reference text appended to the system prompt at runtime.",
    )
    model_override: str | None = Field(
        default=None,
        max_length=36,
        description="Optional Provider UUID. If null, chat layer uses the user's default Provider.",
    )
    is_active: bool = Field(default=True)


class PersonaUpdate(BaseModel):
    """Body for PUT /personas/{id}. All fields optional — only set ones update."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    system_prompt: str | None = Field(default=None, min_length=1)
    knowledge_base: str | None = None
    model_override: str | None = Field(default=None, max_length=36)
    is_active: bool | None = None


class PersonaResponse(BaseModel):
    """Shape returned by GET / POST / PUT /personas endpoints."""

    id: str
    name: str
    system_prompt: str
    knowledge_base: str | None
    model_override: str | None
    is_active: bool
    created_at: datetime