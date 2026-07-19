"""Persona repository — all DB queries for the personas table.

Pure CRUD against the ORM. No encryption (none needed), no masking, no
business validation — those belong in the service layer (Phase 20).

Functions follow the same pattern as provider_repo.py: take a session,
return ORM rows, commit where appropriate.
"""

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Persona


async def create_persona(
    db: AsyncSession,
    user_id: str,
    name: str,
    system_prompt: str,
    knowledge_base: str | None,
    model_override: str | None,
    is_active: bool = True,
) -> Persona:
    """Insert a new persona row. Commits and refreshes to populate id/created_at."""
    persona = Persona(
        user_id=user_id,
        name=name,
        system_prompt=system_prompt,
        knowledge_base=knowledge_base,
        model_override=model_override,
        is_active=is_active,
    )
    db.add(persona)
    await db.commit()
    await db.refresh(persona)
    return persona


async def get_persona_by_id(db: AsyncSession, persona_id: str) -> Persona | None:
    """Look up a persona by its UUID. Does NOT filter by user — caller must."""
    result = await db.execute(select(Persona).where(Persona.id == persona_id))
    return result.scalar_one_or_none()


async def get_persona_by_user_and_name(
    db: AsyncSession, user_id: str, name: str
) -> Persona | None:
    """Look up a persona by (user_id, name). Used for unique-constraint pre-check."""
    result = await db.execute(
        select(Persona).where(Persona.user_id == user_id, Persona.name == name)
    )
    return result.scalar_one_or_none()


async def list_personas_by_user(db: AsyncSession, user_id: str) -> list[Persona]:
    """All personas owned by a user, newest first."""
    result = await db.execute(
        select(Persona)
        .where(Persona.user_id == user_id)
        .order_by(Persona.created_at.desc())
    )
    return list(result.scalars())


async def update_persona(
    db: AsyncSession, persona_id: str, fields: dict
) -> Persona | None:
    """Apply a partial update. fields keys must be valid Persona columns.

    Returns the refreshed row, or None if not found.
    """
    if not fields:
        return await get_persona_by_id(db, persona_id)

    await db.execute(
        update(Persona).where(Persona.id == persona_id).values(**fields)
    )
    await db.commit()
    return await get_persona_by_id(db, persona_id)


async def delete_persona(db: AsyncSession, persona_id: str) -> bool:
    """Delete by id. Returns True if a row was deleted, False otherwise."""
    persona = await get_persona_by_id(db, persona_id)
    if persona is None:
        return False
    await db.delete(persona)
    await db.commit()
    return True