"""Provider registry — turn a provider_id into a live BaseProvider.

Caches instances for 5 min so chat calls don't repeat the DB lookup +
Fernet decrypt + SDK client setup on every request. Edits call
invalidate() to drop the stale instance.

Concurrency: concurrent get_provider(same_id) calls share one in-flight
build via the TTLCache's per-key lock. No duplicate work.

Lifecycle: providers hold httpx clients. close_all() releases them on
app shutdown (Phase 33 will wire this into the FastAPI lifespan).
"""

from __future__ import annotations

from app.core.cache import TTLCache
from app.providers.anthropic import AnthropicProvider
from app.providers.base import BaseProvider
from app.providers.openai import OpenAIProvider


# Module-level singleton. Tests can clear() it between cases.
_cache = TTLCache(maxsize=256, ttl=300.0)


def _class_for(provider_type: str) -> type[BaseProvider]:
    """Map provider.type to the right BaseProvider subclass."""
    if provider_type == "openai":
        return OpenAIProvider
    if provider_type == "anthropic":
        return AnthropicProvider
    if provider_type == "custom":
        # type=custom reuses OpenAIProvider with a custom base_url.
        # Wire format is OpenAI-compatible chat completions.
        return OpenAIProvider
    raise ValueError(f"unknown provider type: {provider_type!r}")


async def _build(provider_id: str) -> BaseProvider:
    """Look up the row, decrypt the key, instantiate the right class."""
    # Import here to avoid circular imports: registry -> db -> security ->
    # crypto providers don't loop, but keeping DB access at the call site
    # lets us swap the data layer in tests.
    from app.db.engine import async_session
    from app.db.models import Provider
    from app.core.security import decrypt_value
    from sqlalchemy import select

    async with async_session() as db:
        result = await db.execute(select(Provider).where(Provider.id == provider_id))
        row = result.scalar_one_or_none()
        if row is None:
            raise LookupError(f"provider {provider_id!r} not found")

        plain_key = decrypt_value(row.api_key)
        cls = _class_for(row.type)
        return cls(api_key=plain_key, model=row.model, base_url=row.base_url)


async def get_provider(provider_id: str) -> BaseProvider:
    """Return a ready-to-use provider, building + caching on miss.

    Concurrent calls for the same id share one in-flight build.
    """
    return await _cache.get_or_set(provider_id, lambda: _build(provider_id))


def invalidate(provider_id: str) -> None:
    """Drop the cached instance for this id. Call after editing the row."""
    _cache.invalidate(provider_id)


async def close_all() -> None:
    """Close every cached provider. Called on app shutdown."""
    # Snapshot values, then drop from cache. Closing while holding the
    # cache reference is fine — httpx.AsyncClient.close() is idempotent.
    instances = list(_cache._data.values())  # noqa: SLF001 — internal access
    _cache.clear()
    for (_deadline, provider) in instances:
        try:
            await provider.close()
        except Exception:
            # Closing an already-closed client shouldn't crash shutdown.
            pass


__all__ = ["get_provider", "invalidate", "close_all"]