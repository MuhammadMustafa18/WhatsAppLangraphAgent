"""OpenAI-compatible LLM client.

Points at FreeLLMAPI by default. The same SDK works against OpenAI,
Azure, Groq, or any other OpenAI-compatible endpoint — just change
OPENAI_BASE_URL and OPENAI_API_KEY in .env.

The OpenAI client is constructed lazily on first use. This module is
imported at app boot, BEFORE load_dotenv() runs in main.py — so we
can't read OPENAI_API_KEY at import time without coupling import order.
"""

from __future__ import annotations

import os
from functools import lru_cache

from openai import OpenAI


@lru_cache(maxsize=1)
def _get_client() -> OpenAI:
    """Build the OpenAI client on first use, when .env has been loaded."""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    base_url = os.environ.get("OPENAI_BASE_URL", "http://127.0.0.1:31415/v1")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is unset. Add it to .env (and restart uvicorn)."
        )
    return OpenAI(base_url=base_url, api_key=api_key)


def chat(system: str, user: str) -> str:
    """Single-turn chat. Returns the model's reply text."""
    # `auto` lets FreeLLMAPI's router pick the best available model.
    # Pin a specific model name (e.g. "gemini-2.5-flash") to skip routing.
    model = os.environ.get("OPENAI_MODEL", "auto")
    resp = _get_client().chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return (resp.choices[0].message.content or "").strip()