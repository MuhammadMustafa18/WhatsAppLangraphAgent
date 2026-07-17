"""OpenAI-compatible LLM client.

Points at FreeLLMAPI by default. The same SDK works against OpenAI,
Azure, Groq, or any other OpenAI-compatible endpoint — just change
OPENAI_BASE_URL and OPENAI_API_KEY in .env.

The OpenAI client is constructed lazily on first use. This module is
imported at app boot, BEFORE load_dotenv() runs in main.py — so we
can't read OPENAI_API_KEY at import time without coupling import order.
"""

from __future__ import annotations

from functools import lru_cache

from openai import OpenAI

from app.core.config import get_settings


@lru_cache(maxsize=1)
def _get_client() -> OpenAI:
    """Build the OpenAI client on first use, when .env has been loaded."""
    settings = get_settings()
    if not settings.OPENAI_API_KEY:
        raise RuntimeError(
            "OPENAI_API_KEY is unset. Add it to .env (and restart uvicorn)."
        )
    return OpenAI(base_url=settings.OPENAI_BASE_URL, api_key=settings.OPENAI_API_KEY)


def chat(system: str, user: str, model: str | None = None) -> str:
    """Single-turn chat. Returns the model's reply text.

    `model=None` lets FreeLLMAPI's router pick (OPENAI_MODEL=auto).
    Pass a specific model name (e.g. "gpt-oss-120b") to skip routing.
    """
    settings = get_settings()
    chosen = model or settings.OPENAI_MODEL
    resp = _get_client().chat.completions.create(
        model=chosen,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return (resp.choices[0].message.content or "").strip()