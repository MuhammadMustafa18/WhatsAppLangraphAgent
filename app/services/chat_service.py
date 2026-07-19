"""Chat service — streaming chat for the in-app UI.

Phase 23 owns the in-app Chat Preview path. The webhook path stays
on graph.ainvoke() — see main.py. Different surface, different
latency profile, different consumer (Tauri UI vs OpenWA gateway).

What this service does:
  1. Resolve the persona (persona_id explicit, else user's first active).
  2. Resolve the provider (provider_id explicit, else persona's
     model_override, else user's default).
  3. Build the multi-turn messages list (history + current user).
  4. Open the BaseProvider via provider_registry (cached).
  5. Yield each token from provider.chat_stream() to the caller.
  6. After the stream ends, record the turn to the conversations
     table with channel='app'.

Why the record happens AFTER the stream (not before): if the LLM
fails mid-stream, we don't want a half-reply in the user's history.
Failing the whole turn is the right call.

Auth + user resolution live in the controller (app/api/chat.py).
This service takes a User object already.
"""

from __future__ import annotations

from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import async_session
from app.db.models import Persona as PersonaRow, Provider as ProviderRow, User
from app.graph import _resolve_persona, _resolve_provider
from app.providers import registry as provider_registry


async def stream(
    user: User,
    message: str,
    history: list[dict] | None = None,
    persona_id: str | None = None,
    provider_id: str | None = None,
    thread_id: str = "in-app-default",
) -> AsyncIterator[tuple[str, str]]:
    """Yield (event_type, payload) tuples as the reply streams.

    Event types yielded:
      ("token", "<delta>")        — one per LLM token
      ("done", "<full reply>")    — exactly once, after the stream ends

    Why tuples and not just strings: the controller translates each
    tuple into an SSE event with a type discriminator so the UI can
    know when the reply is final. Token events are partial; done is
    final.

    The conversation record is written after the full reply is
    assembled but BEFORE the done event is yielded. The UI gets the
    done event once the row is committed.
    """
    history = history or []

    # Build a state-shaped dict for the resolve helpers (matches
    # the shape they accept from generate()).
    state = {"message": message, "persona_id": persona_id, "provider_id": provider_id}

    # Resolve persona + provider from DB. Two DB lookups on the
    # first turn of a session — TTLCache will absorb subsequent
    # ones for the same provider_id.
    async with async_session() as db:
        persona: PersonaRow = await _resolve_persona(db, user.id, state)
        provider_row: ProviderRow = await _resolve_provider(db, user.id, state, persona)

    system_prompt = persona.system_prompt
    if persona.knowledge_base:
        system_prompt = f"{persona.system_prompt}\n\n{persona.knowledge_base}"

    msgs: list[dict] = list(history)
    msgs.append({"role": "user", "content": message})

    provider = await provider_registry.get_provider(provider_row.id)

    # Accumulate tokens into a full reply, then emit per-token events
    # to the caller. If anything in the stream raises, we let the
    # exception propagate — the controller catches and sends an
    # SSE error event.
    full_reply_parts: list[str] = []
    async for delta in provider.chat_stream(
        msgs, system=system_prompt, max_tokens=provider_row.max_tokens,
    ):
        full_reply_parts.append(delta)
        yield ("token", delta)

    full_reply = "".join(full_reply_parts)

    # Record the completed turn. Sync write — Phase 30 will move it
    # off the critical path later. Errors are logged but never
    # raised; the user already got their reply.
    new_history = history + [
        {"role": "user", "content": message},
        {"role": "assistant", "content": full_reply},
    ]
    try:
        from app.services import conversation_service
        async with async_session() as db:
            await conversation_service.record_turn(
                db,
                user_id=user.id,
                thread_id=thread_id,
                messages=new_history,
                persona_id=persona.id,
                channel="app",
            )
    except Exception:
        import logging
        logging.getLogger("app.chat").exception(
            "failed to record chat turn (thread=%s user=%s)",
            thread_id, user.id,
        )

    yield ("done", full_reply)


__all__ = ["stream"]