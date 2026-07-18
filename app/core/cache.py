"""TTL cache — bounded, async-aware key/value store with per-entry expiry.

Generic utility used by the provider registry (Phase 17) and elsewhere.
Same shape as cachetools.TTLCache but built around asyncio.Lock so
concurrent misses don't build the same value twice.

Not thread-safe — only safe under asyncio. If we ever need multi-thread,
wrap with threading.Lock.
"""

import asyncio
import time
from typing import Any, Callable, Awaitable


class TTLCache:
    """Async-friendly TTL cache.

    Entries expire `ttl` seconds after they're written. On miss, the
    factory is called inside a per-key lock so concurrent misses for the
    same key share the in-flight build.

    Eviction: when full, the entry closest to expiry is dropped first
    (smallest absolute deadline). Bounded by `maxsize`.
    """

    def __init__(self, maxsize: int = 256, ttl: float = 300.0) -> None:
        self.maxsize = maxsize
        self.ttl = ttl
        self._data: dict[str, tuple[float, Any]] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    def get(self, key: str) -> Any | None:
        """Return cached value or None if missing/expired.

        Does NOT call factory. Use get_or_set for that.
        Expired entries are pruned lazily on access.
        """
        entry = self._data.get(key)
        if entry is None:
            return None
        deadline, value = entry
        if deadline <= time.monotonic():
            del self._data[key]
            return None
        return value

    async def get_or_set(
        self,
        key: str,
        factory: Callable[[], Awaitable[Any]],
    ) -> Any:
        """Return cached value, or call factory() and cache the result.

        Concurrent calls for the same key share one factory invocation.
        """
        # Fast path: cache hit.
        existing = self.get(key)
        if existing is not None:
            return existing

        # Slow path: acquire a per-key lock so concurrent misses for the
        # same key don't double-build. We use a global lock to create the
        # per-key lock atomically, then release it before calling factory.
        async with self._global_lock:
            lock = self._locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[key] = lock

        async with lock:
            # Re-check after acquiring the lock — another coroutine may
            # have populated the cache while we were waiting.
            existing = self.get(key)
            if existing is not None:
                return existing

            value = await factory()
            self._maybe_evict()
            self._data[key] = (time.monotonic() + self.ttl, value)
            return value

    def invalidate(self, key: str) -> None:
        """Drop a key from the cache. Idempotent."""
        self._data.pop(key, None)
        # Keep the lock around; it's tiny and harmless.

    def clear(self) -> None:
        """Drop everything."""
        self._data.clear()

    def _maybe_evict(self) -> None:
        """If at capacity, drop the entry with the smallest deadline."""
        if len(self._data) < self.maxsize:
            return
        # Find entry with earliest expiry. dict preserves insertion order,
        # so this is O(n) scan.
        victim_key = min(self._data, key=lambda k: self._data[k][0])
        del self._data[victim_key]

    def __len__(self) -> int:
        return len(self._data)

    def __contains__(self, key: str) -> bool:
        return self.get(key) is not None


__all__ = ["TTLCache"]