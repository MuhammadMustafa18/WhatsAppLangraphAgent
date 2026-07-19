"""Persona service — business logic for the /personas endpoint.

Sits between the controller (HTTP) and the repository (DB). Owns:
  - ownership checks (404 if a user requests someone else's persona —
    don't leak existence via different status codes)
  - FK validation: if model_override is set, confirm the provider exists
    AND belongs to this user. Otherwise we'd let users wire their
    personas to other users' providers.
  - ORM-row → response-shaped dict translation (to_response)
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Persona, User
from app.repositories import persona_repo, provider_repo
from app.schemas.persona import PersonaCreate, PersonaUpdate


async def _validate_model_override(
    db: AsyncSession, user: User, model_override: str | None
) -> str | None:
    """If a model_override is provided, confirm it points at a provider
    the calling user owns. Returns the override unchanged on success,
    or None if it should be cleared (provider missing or not owned).

    Clearing (instead of raising) matches the user-friendly intent: a
    broken link shouldn't block the save. The chat layer will then fall
    back to the user's default provider.
    """
    if model_override is None:
        return None

    provider = await provider_repo.get_provider_by_id(db, model_override)
    if provider is None or provider.user_id != user.id:
        # Silently drop the bad FK; chat layer handles null gracefully.
        return None
    return model_override


async def create(
    db: AsyncSession, user: User, data: PersonaCreate
) -> Persona:
    """Create a persona. Validates model_override belongs to this user.

    Raises ValueError if a persona with the same name already exists for
    this user — the controller converts that to a 409. We pre-check
    rather than letting the UNIQUE constraint crash as a 500.
    """
    existing = await persona_repo.get_persona_by_user_and_name(db, user.id, data.name)
    if existing is not None:
        raise ValueError(f"persona named {data.name!r} already exists")

    override = await _validate_model_override(db, user, data.model_override)
    return await persona_repo.create_persona(
        db,
        user_id=user.id,
        name=data.name,
        system_prompt=data.system_prompt,
        knowledge_base=data.knowledge_base,
        model_override=override,
        is_active=data.is_active,
    )


async def list_for_user(db: AsyncSession, user: User) -> list[Persona]:
    """All personas owned by this user, newest first."""
    return await persona_repo.list_personas_by_user(db, user.id)


async def get_or_404(
    db: AsyncSession, user: User, persona_id: str
) -> Persona | None:
    """Return the row if it exists AND user.id matches. None otherwise.

    Returning None for "not yours" too — don't leak existence via
    different status codes.
    """
    row = await persona_repo.get_persona_by_id(db, persona_id)
    if row is None or row.user_id != user.id:
        return None
    return row


async def update(
    db: AsyncSession,
    user: User,
    persona_id: str,
    data: PersonaUpdate,
) -> Persona | None:
    """Partial update. Re-validates model_override if provided.

    Returns the refreshed row, or None if not owned / not found.
    """
    row = await get_or_404(db, user, persona_id)
    if row is None:
        return None

    # model_dump(exclude_unset=True) gives only the fields the caller
    # actually sent. Missing fields aren't included in the dict.
    fields = data.model_dump(exclude_unset=True)

    # If model_override was sent, re-validate it. If it's None in the
    # payload, that's the caller explicitly clearing the link.
    if "model_override" in fields:
        fields["model_override"] = await _validate_model_override(
            db, user, fields["model_override"]
        )

    return await persona_repo.update_persona(db, persona_id, fields)


async def delete(
    db: AsyncSession, user: User, persona_id: str
) -> bool:
    """Remove the persona. Returns False if not owned / not found."""
    row = await get_or_404(db, user, persona_id)
    if row is None:
        return False
    return await persona_repo.delete_persona(db, persona_id)


def to_response(persona: Persona) -> dict:
    """Convert an ORM row to a response-shaped dict.

    Plain 1:1 mapping — no encryption, no masking. Personas have no
    secrets.
    """
    return {
        "id": persona.id,
        "name": persona.name,
        "system_prompt": persona.system_prompt,
        "knowledge_base": persona.knowledge_base,
        "model_override": persona.model_override,
        "is_active": persona.is_active,
        "created_at": persona.created_at,
    }


__all__ = [
    "create",
    "list_for_user",
    "get_or_404",
    "update",
    "delete",
    "to_response",
]