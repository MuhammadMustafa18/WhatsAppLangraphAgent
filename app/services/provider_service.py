"""Provider service — business logic for the /providers endpoint.

Sits between the controller (HTTP) and the repository (DB). Owns:
  - encryption on write (plaintext -> Fernet ciphertext)
  - decryption on read (ciphertext -> plaintext) — but we never return
    the plaintext to clients, only to the registry when it builds a
    live BaseProvider
  - ownership checks (404 if a user requests someone else's provider)
  - cache invalidation after edits (so the registry rebuilds)
  - masking plaintext into "sk-...last4" for response shapes
  - the default-switching invariant (one default per user)
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_value, encrypt_value
from app.db.models import Provider, User
from app.providers import registry
from app.providers.anthropic import AnthropicProvider
from app.providers.openai import OpenAIProvider
from app.repositories import provider_repo
from app.schemas.provider import ProviderCreate, ProviderUpdate


def mask_key(plaintext: str) -> str:
    """Render an api_key as 'sk-...last4' for safe API responses.

    Even very short keys get the prefix — predictable shape beats ad-hoc
    handling for edge cases.
    """
    return f"...{plaintext[-4:]}"


def to_response(provider: Provider, plaintext: str | None = None) -> dict:
    """Convert an ORM row to a response-shaped dict.

    Always includes api_key_masked. If plaintext is provided, also
    includes api_key_plain — used exactly once on POST /providers.
    """
    out = {
        "id": provider.id,
        "name": provider.name,
        "type": provider.type,
        "base_url": provider.base_url,
        "api_key_masked": mask_key(decrypt_value(provider.api_key)),
        "model": provider.model,
        "max_tokens": provider.max_tokens,
        "is_default": provider.is_default,
        "created_at": provider.created_at,
    }
    if plaintext is not None:
        out["api_key_plain"] = plaintext
    return out


async def create(
    db: AsyncSession, user: User, data: ProviderCreate
) -> tuple[Provider, str]:
    """Create a provider. Returns (row, plaintext_api_key).

    The plaintext is returned so the controller can include it in the
    one-shot create response. We don't store plaintext — encrypt_value()
    runs before the row hits the DB.

    First provider? Make it default automatically so the user can
    start chatting immediately without an extra step.
    """
    is_default = (await provider_repo.list_providers_by_user(db, user.id)) == []

    encrypted = encrypt_value(data.api_key)
    row = await provider_repo.create_provider(
        db,
        user_id=user.id,
        name=data.name,
        type_=data.type,
        base_url=data.base_url,
        api_key_enc=encrypted,
        model=data.model,
        max_tokens=data.max_tokens,
        is_default=is_default,
    )
    return row, data.api_key


async def list_for_user(db: AsyncSession, user: User) -> list[Provider]:
    """All providers owned by this user, newest first."""
    return await provider_repo.list_providers_by_user(db, user.id)


async def get_or_404(
    db: AsyncSession, user: User, provider_id: str
) -> Provider | None:
    """Return the row if it exists AND user.id matches. None otherwise.

    Returning None for "not yours" too — don't leak existence via
    different status codes.
    """
    row = await provider_repo.get_provider_by_id(db, provider_id)
    if row is None or row.user_id != user.id:
        return None
    return row


async def update(
    db: AsyncSession,
    user: User,
    provider_id: str,
    data: ProviderUpdate,
) -> Provider | None:
    """Partial update. Encrypts api_key if provided. Invalidates cache.

    Returns the refreshed row, or None if not owned / not found.
    """
    row = await get_or_404(db, user, provider_id)
    if row is None:
        return None

    # model_dump(exclude_unset=True) gives only the fields the caller
    # actually sent. Missing fields aren't included in the dict.
    fields = data.model_dump(exclude_unset=True)

    # The DB column is `api_key` (ciphertext); the DTO field is also
    # `api_key`. If api_key was sent, encrypt before storing.
    if "api_key" in fields:
        fields["api_key"] = encrypt_value(fields["api_key"])

    updated = await provider_repo.update_provider(db, provider_id, fields)
    if updated is not None:
        registry.invalidate(provider_id)
    return updated


async def delete(
    db: AsyncSession, user: User, provider_id: str
) -> bool:
    """Remove the provider. Returns False if not owned / not found."""
    row = await get_or_404(db, user, provider_id)
    if row is None:
        return False
    ok = await provider_repo.delete_provider(db, provider_id)
    if ok:
        registry.invalidate(provider_id)
    return ok


async def validate_provider(
    db: AsyncSession, user: User, provider_id: str
) -> bool | None:
    """Hit the real provider API to confirm the key works.

    Returns True/False for owned providers, None for not-owned.
    Builds the provider instance directly here rather than going through
    the registry — validation is a one-off check, no point caching.
    """
    row = await get_or_404(db, user, provider_id)
    if row is None:
        return None

    plain = decrypt_value(row.api_key)
    if row.type == "anthropic":
        provider = AnthropicProvider(plain, row.model, row.base_url)
    else:
        provider = OpenAIProvider(plain, row.model, row.base_url)

    try:
        ok = await provider.validate()
    finally:
        await provider.close()
    return ok


async def set_default(
    db: AsyncSession, user: User, provider_id: str
) -> Provider | None:
    """Make this provider the user's default. Returns the row, or None."""
    row = await get_or_404(db, user, provider_id)
    if row is None:
        return None
    return await provider_repo.set_default_provider(db, user.id, provider_id)


__all__ = [
    "create",
    "list_for_user",
    "get_or_404",
    "update",
    "delete",
    "validate_provider",
    "set_default",
    "mask_key",
    "to_response",
]