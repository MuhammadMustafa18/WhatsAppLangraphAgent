"""Abstract base class for LLM providers.

Every concrete provider (OpenAI, Anthropic, custom OpenAI-compatible) must
implement this interface. The chat service in Phase 23 only knows about
this ABC — it doesn't branch on provider type. Translation to each
provider's wire format happens inside the implementation.

Input shape (unified, OpenAI-style):
    messages = [
        {"role": "system", "content": "You are ..."},
        {"role": "user",   "content": "Hi"},
        {"role": "assistant", "content": "Hello!"},
    ]

The system prompt also has a top-level shortcut via the `system` arg on
chat/chat_stream. The Anthropic provider translates that into its
required separate system param. Implementations may merge or override as
appropriate — the contract is just "model sees the system text".

Streaming yields raw string chunks (typically tokens or small token
groups). When we need richer events (tool calls, structured output),
we'll widen this to a StreamEvent union — until then, str is enough.
"""

from abc import ABC, abstractmethod
from typing import AsyncIterator


class BaseProvider(ABC):
    """Common interface for all LLM providers.

    Subclasses MUST:
      - Accept (api_key, model, base_url=None) in __init__.
      - Override chat() and chat_stream() with concrete implementations.
      - Override validate() to do a real check (e.g. GET /models).
    """

    api_key: str
    model: str
    base_url: str | None

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        system: str | None = None,
        max_tokens: int = 1024,
    ) -> str:
        """Send messages, return the full assistant reply as a single string."""
        ...

    @abstractmethod
    def chat_stream(
        self,
        messages: list[dict],
        system: str | None = None,
        max_tokens: int = 1024,
    ) -> AsyncIterator[str]:
        """Send messages, yield reply chunks as they arrive.

        Returned object is an async iterator — call sites do
            async for chunk in provider.chat_stream(messages): ...
        Must be an async generator (yield inside an `async def`), not a
        plain method that returns a list.
        """
        ...

    @abstractmethod
    async def validate(self) -> bool:
        """Confirm the api_key + base_url are usable. Should hit the
        provider's API (e.g. GET /models) rather than just check
        non-empty, so misconfigured keys surface at save time."""
        ...

    async def __aenter__(self) -> "BaseProvider":
        return self

    async def __aexit__(self, *exc) -> None:
        await self.close()

    async def close(self) -> None:
        """Release any held resources (HTTP clients, etc.).
        Default is no-op for providers that don't hold resources."""
        return None


__all__ = ["BaseProvider"]