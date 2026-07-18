"""Provider repository — all DB queries for the providers table.

Pure CRUD against the ORM. No encryption, no masking, no validation —
those belong in the service layer. The caller passes already-encrypted
ciphertext as `api_key_enc`; the repo stores it verbatim.

Functions follow the same pattern as user_repo.py: take a session,
return ORM rows, commit where appropriate.
"""

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Provider


async def create_provider(
    db: AsyncSession,
    user_id: str,
    name: str,
    type_: str,
    base_url: str | None,
    api_key_enc: str,
    model: str,
    max_tokens: int = 1024,
    is_default: bool = False,
) -> Provider:
    """Insert a new provider row. Commits and refreshes to populate id/created_at."""
    provider = Provider(
        user_id=user_id,
        name=name,
        type=type_,
        base_url=base_url,
        api_key=api_key_enc,
        model=model,
        max_tokens=max_tokens,
        is_default=is_default,
    )
    db.add(provider)
    await db.commit()
    await db.refresh(provider)
    return provider


async def get_provider_by_id(db: AsyncSession, provider_id: str) -> Provider | None:
    """Look up a provider by its UUID. Does NOT filter by user — caller must."""
    result = await db.execute(select(Provider).where(Provider.id == provider_id))
    return result.scalar_one_or_none()


async def list_providers_by_user(db: AsyncSession, user_id: str) -> list[Provider]:
    """All providers owned by a user, newest first."""
    result = await db.execute(
        select(Provider)
        .where(Provider.user_id == user_id)
        .order_by(Provider.created_at.desc())
    )
    return list(result.scalars())


async def get_default_provider(db: AsyncSession, user_id: str) -> Provider | None:
    """The user's is_default=True provider, or None if none set."""
    result = await db.execute(
        select(Provider)
        .where(Provider.user_id == user_id, Provider.is_default.is_(True))
    )
    return result.scalar_one_or_none()


async def update_provider(
    db: AsyncSession, provider_id: str, fields: dict
) -> Provider | None:
    """Apply a partial update. fields keys must be valid Provider columns.

    Pass `api_key` as already-encrypted ciphertext if updating it.
    Returns the refreshed row, or None if not found.
    """
    if not fields:
        return await get_provider_by_id(db, provider_id)

    await db.execute(
        update(Provider).where(Provider.id == provider_id).values(**fields)
    )
    await db.commit()
    return await get_provider_by_id(db, provider_id)


async def delete_provider(db: AsyncSession, provider_id: str) -> bool:
    """Delete by id. Returns True if a row was deleted, False otherwise."""
    provider = await get_provider_by_id(db, provider_id)
    if provider is None:
        return False
    await db.delete(provider)
    await db.commit()
    return True


async def clear_default_for_user(db: AsyncSession, user_id: str) -> None:
    """Set is_default=False on every provider for a user. No-op if none default."""
    await db.execute(
        update(Provider)
        .where(Provider.user_id == user_id, Provider.is_default.is_(True))
        .values(is_default=False)
    )
    await db.commit()


async def set_default_provider(
    db: AsyncSession, user_id: str, provider_id: str
) -> Provider | None:
    """Make this provider the user's default. Clears any prior default first
    so the (per-user) 'one default' invariant holds. Returns the refreshed row,
    or None if the provider doesn't exist or isn't owned by user_id.
    """
    provider = await get_provider_by_id(db, provider_id)
    if provider is None or provider.user_id != user_id:
        return None
    await clear_default_for_user(db, user_id)
    await db.execute(
        update(Provider)
        .where(Provider.id == provider_id)
        .values(is_default=True)
    )
    await db.commit()
    await db.refresh(provider)
    return provider