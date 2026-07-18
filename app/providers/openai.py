"""OpenAI-compatible chat provider.

Speaks OpenAI's /chat/completions API. Also works against any OpenAI-
compatible endpoint (LM Studio, Ollama, vLLM, Azure OpenAI, etc.) — the
caller just supplies a different base_url. The `type=custom` Provider
row reuses this class verbatim with no subclassing.
"""

from __future__ import annotations

import openai

from app.providers.base import BaseProvider


def _inject_system(messages: list[dict], system: str | None) -> list[dict]:
    """Prepend a system message if one was passed via the shortcut arg.

    OpenAI's API accepts system as a regular message in the list. We
    prepend so it dominates any system messages the caller already
    embedded in `messages`.
    """
    if not system:
        return messages
    return [{"role": "system", "content": system}, *messages]


class OpenAIProvider(BaseProvider):
    """Async OpenAI / OpenAI-compatible chat completions client."""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str | None = None,
    ) -> None:
        super().__init__(api_key, model, base_url)
        # AsyncOpenAI returns an httpx-based async client. base_url=None
        # defaults to https://api.openai.com/v1.
        self._client = openai.AsyncOpenAI(
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
        msgs = _inject_system(messages, system)
        resp = await self._client.chat.completions.create(
            model=self.model,
            messages=msgs,
            max_tokens=max_tokens,
        )
        # choices[0].message.content is str | None — guard against
        # providers that return tool_calls only.
        return resp.choices[0].message.content or ""

    async def chat_stream(
        self,
        messages: list[dict],
        system: str | None = None,
        max_tokens: int = 1024,
    ):
        msgs = _inject_system(messages, system)
        stream = await self._client.chat.completions.create(
            model=self.model,
            messages=msgs,
            max_tokens=max_tokens,
            stream=True,
        )
        async for chunk in stream:
            # Each chunk has at most one delta.content. Some chunks are
            # role-only or finish_reason-only — skip those.
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content

    async def validate(self) -> bool:
        """Hit GET /models to confirm the key works at this base_url.

        Returns False on any exception (bad key, wrong base_url, network).
        Used by Phase 18's service when the user saves a Provider.
        """
        try:
            await self._client.models.list()
            return True
        except Exception:
            return False

    async def close(self) -> None:
        await self._client.close()


__all__ = ["OpenAIProvider"]