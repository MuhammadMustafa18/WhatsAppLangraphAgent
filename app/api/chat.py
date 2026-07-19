"""Chat controller — POST /chat for the in-app Tauri UI.

Returns Server-Sent Events. Two event types:
  data: {"type":"token", "delta":"hello"}      — incremental token
  data: {"type":"done",  "reply":"hello world","persona":"support", "provider":"gpt-4o"}
                                                — final reply

Why SSE and not WebSocket:
  - The Tauri UI sends ONE message and gets ONE reply. Bidirectional
    is overkill; SSE is a strictly simpler contract.
  - EventSource in the browser handles reconnection, last-event-id,
    and Content-Type negotiation for free. Tauri uses the same fetch
    primitives as a browser.
  - We can swap to WebSocket later if we add voice/multi-modal; SSE
    gives us a working starting point today.

The controller is thin: parse request, call service, translate
yields into SSE events. No DB calls, no business logic — those live
in chat_service.stream().

Auth: requires a JWT (same as /providers, /personas). The user is
resolved from the token; we never trust the client-supplied user_id.

History: optional in the request body. If the client sends prior
messages, we pass them as context to the LLM. We do NOT load history
from the conversation table automatically — that's a future polish
(Phase 34 will wire the History tab to feed prior turns back in).
For now, every /chat call is one-shot.
"""

from __future__ import annotations

import json
from typing import AsyncIterator

from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

from app.core.deps import get_current_user
from app.db.models import User
from app.schemas.chat import ChatRequest
from app.services import chat_service

router = APIRouter(prefix="/chat", tags=["chat"])


def _sse_format(event_type: str, payload: dict) -> dict:
    """Shape one SSE event.

    sse_starlette sends each yielded dict as a JSON-encoded `data:` line.
    The `event:` field maps to EventSource.onmessage vs on[event] handlers.
    """
    return {
        "event": event_type,
        "data": json.dumps(payload),
    }


async def _events(
    user: User,
    message: str,
    history: list[dict] | None,
    persona_id: str | None,
    provider_id: str | None,
    thread_id: str,
) -> AsyncIterator[dict]:
    """Adapter from chat_service.stream()'s tuples to SSE wire format.

    Yielded shapes:
      {"event": "token", "data": "..."}      — for each LLM token
      {"event": "done",  "data": "..."}      — once at the end
      {"event": "error", "data": "..."}      — if the stream raises
    """
    final_reply: str | None = None
    persona_name: str | None = None
    provider_name: str | None = None

    try:
        async for kind, payload in chat_service.stream(
            user=user,
            message=message,
            history=history,
            persona_id=persona_id,
            provider_id=provider_id,
            thread_id=thread_id,
        ):
            if kind == "token":
                yield _sse_format("token", {"delta": payload})
            elif kind == "done":
                final_reply = payload
                # We need persona + provider names for the done event
                # footer. chat_service doesn't return them today; resolve
                # here from the DB for the metadata payload. A second
                # DB hit is acceptable — the user is waiting for the
                # text, not the metadata.
                from app.db.engine import async_session
                from app.graph import _resolve_persona, _resolve_provider
                state = {
                    "message": message,
                    "persona_id": persona_id,
                    "provider_id": provider_id,
                }
                async with async_session() as db:
                    p = await _resolve_persona(db, user.id, state)
                    pr = await _resolve_provider(db, user.id, state, p)
                    persona_name = p.name
                    provider_name = pr.name
                yield _sse_format("done", {
                    "reply": final_reply,
                    "persona": persona_name,
                    "provider": provider_name,
                })
    except Exception as exc:
        import logging
        logging.getLogger("app.chat").exception("chat stream failed")
        yield _sse_format("error", {"message": str(exc)})


@router.post("")
async def post_chat(
    data: ChatRequest,
    user: User = Depends(get_current_user),
):
    """Stream a chat reply via SSE.

    Request body: ChatRequest (message, persona_id?, provider_id?).
    Response: text/event-stream with token + done events.

    The thread_id defaults to a constant for in-app chats; Phase 34
    will thread this through the Tauri Chat Preview so the user can
    have multiple conversations.
    """
    return EventSourceResponse(
        _events(
            user=user,
            message=data.message,
            history=None,
            persona_id=data.persona_id,
            provider_id=data.provider_id,
            thread_id="in-app-default",
        )
    )