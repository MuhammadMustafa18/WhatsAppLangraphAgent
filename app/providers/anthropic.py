"""Anthropic Messages API provider.

Implements BaseProvider against anthropic.AsyncAnthropic. Translates the
unified OpenAI-style input shape into Anthropic's wire format:

  - system prompt goes in a TOP-LEVEL `system` field, not a message
    with role="system" (Anthropic caches it; embedding in messages
    misses the cache).
  - content can be a list of blocks (text/image/tool_use); we only
    handle str content for now. A list raises so the caller knows
    we don't support it.
  - max_tokens is REQUIRED by the Anthropic API.

The chat service (Phase 23) doesn't see any of this — it just calls
provider.chat(messages, system=...).
"""

from __future__ import annotations

import anthropic

from app.providers.base import BaseProvider


class UnsupportedContentError(ValueError):
    """Raised when a message uses a content shape this provider can't translate."""


def _separate_system(messages: list[dict], system_arg: str | None) -> tuple[list[dict], str | None]:
    """Split out the system prompt and strip it from the messages list.

    Resolution order for the final system text:
      1. Caller's `system` arg (e.g. persona prompt) — wins if non-empty.
      2. Any {"role":"system"} messages in `messages` — joined by newline.
      3. None.

    Returns (filtered_messages, system_text).
    """
    if system_arg:
        filtered = [m for m in messages if m["role"] != "system"]
        return filtered, system_arg

    embedded = [m["content"] for m in messages if m["role"] == "system"]
    filtered = [m for m in messages if m["role"] != "system"]
    return filtered, ("\n".join(embedded) if embedded else None)


def _validate_text_only(messages: list[dict]) -> None:
    """Anthropic accepts content as str or list[block]; we only handle str.

    A list-shaped content (multi-block) is a real Anthropic feature, but
    surfacing it would force the chat service to know about provider-
    specific block types. We fail loudly instead.
    """
    for m in messages:
        content = m.get("content")
        if content is not None and not isinstance(content, str):
            raise UnsupportedContentError(
                "AnthropicProvider only supports str content. "
                "Multi-block content (images, tool_use) is not implemented "
                "in this provider."
            )


class AnthropicProvider(BaseProvider):
    """Async Anthropic Messages API client."""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str | None = None,
    ) -> None:
        super().__init__(api_key, model, base_url)
        # AsyncAnthropic defaults to https://api.anthropic.com. base_url
        # is useful for proxies (see ANTHROPIC_BASE_URL in .env).
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key,
            base_url=base_url,
            timeout=60.0,
        )

    async def chat(
        self,
        messages: list[dict],
        system: str | None = None,
        max_tokens: int = 1024,
    ) -> str:
        filtered, system_text = _separate_system(messages, system)
        _validate_text_only(filtered)
        resp = await self._client.messages.create(
            model=self.model,
            system=system_text,  # None is allowed — Anthropic skips the field
            messages=filtered,
            max_tokens=max_tokens,
        )
        # resp.content is a list of blocks. For a plain text reply the first
        # (and only) block is TextBlock; .text is the string.
        return resp.content[0].text

    async def chat_stream(
        self,
        messages: list[dict],
        system: str | None = None,
        max_tokens: int = 1024,
    ):
        filtered, system_text = _separate_system(messages, system)
        _validate_text_only(filtered)
        async with self._client.messages.stream(
            model=self.model,
            system=system_text,
            messages=filtered,
            max_tokens=max_tokens,
        ) as stream:
            # text_stream yields just the text deltas, skipping any
            # tool_use blocks (we don't support tools here).
            async for text in stream.text_stream:
                yield text

    async def validate(self) -> bool:
        """Hit GET /v1/models to confirm the key works.

        Returns False on any exception (bad key, wrong base_url, network).
        """
        try:
            # Anthropic's models.list takes limit; using 1 keeps the response tiny.
            await self._client.models.list(limit=1)
            return True
        except Exception:
            return False

    async def close(self) -> None:
        await self._client.close()


__all__ = ["AnthropicProvider", "UnsupportedContentError"]