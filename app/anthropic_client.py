"""Anthropic-compatible LLM client.

Points at a custom Anthropic-compatible proxy (e.g. minimax). The
official anthropic SDK works against any Anthropic-Messages-compatible
endpoint — just change ANTHROPIC_BASE_URL.

Lazy client construction (same pattern as app/llm.py) so importing
this module at app boot doesn't read env vars before load_dotenv runs.
"""

from __future__ import annotations

from functools import lru_cache

from anthropic import Anthropic

from app.core.config import get_settings


@lru_cache(maxsize=1)
def _get_client() -> Anthropic:
    """Build the Anthropic client on first use, when .env has been loaded."""
    settings = get_settings()
    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is unset. Add it to .env (and restart uvicorn)."
        )
    if not settings.ANTHROPIC_BASE_URL:
        raise RuntimeError(
            "ANTHROPIC_BASE_URL is unset. Add it to .env (and restart uvicorn)."
        )
    return Anthropic(base_url=settings.ANTHROPIC_BASE_URL, api_key=settings.ANTHROPIC_API_KEY)


def chat(system: str, user: str) -> str:
    """Single-turn Anthropic Messages call. Returns the model's reply text."""
    settings = get_settings()
    resp = _get_client().messages.create(
        model=settings.ANTHROPIC_MODEL,
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    # Anthropic returns a list of content blocks. The reply is text blocks
    # concatenated. For a single-turn chat there's usually one block.
    parts = []
    for block in resp.content:
        if getattr(block, "type", None) == "text":
            parts.append(block.text)
    return "\n".join(parts).strip() or "(empty response)"