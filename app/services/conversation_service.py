"""Conversation service — business logic for /history and runtime writes.

Phase 22 owns the cap-at-50 rule: every write trims the messages list
to the most recent N turns. Repo just persists what's given; service
decides what gets sent.

Phase 23 will read from this service via a REST endpoint:
  GET /history                  — list user's threads
  GET /history/{thread_id}      — one thread's full messages
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Conversation
from app.repositories import conversation_repo


# Maximum turns retained in the messages JSON column. Older turns
# remain in the checkpointer (data/checkpoints.sqlite) but won't be
# queryable via /history. Raised later if real users complain.
HISTORY_CAP = 50


def _cap(messages: list[dict], limit: int = HISTORY_CAP) -> list[dict]:
    """Keep the last `limit` messages. Drops oldest first.

    We always keep the assistant + user pair structure intact; the
    LLM only ever appends in (user, assistant) order, so the cap is
    a clean slice off the front.
    """
    if len(messages) <= limit:
        return list(messages)
    return list(messages[-limit:])


async def record_turn(
    db: AsyncSession,
    user_id: str,
    thread_id: str,
    messages: list[dict],
    persona_id: str | None = None,
    channel: str = "whatsapp",
) -> Conversation:
    """Called from generate() after a successful LLM turn.

    Replaces the conversation row's messages with the cap'd list.
    Updates persona_id and last_message_at. Sync write — Phase 30's
    Job queue will move this off the critical path later.
    """
    capped = _cap(messages)
    return await conversation_repo.upsert_conversation(
        db,
        user_id=user_id,
        thread_id=thread_id,
        messages=capped,
        persona_id=persona_id,
        channel=channel,
    )


async def list_threads(
    db: AsyncSession, user_id: str, channel: str | None = None
) -> list[Conversation]:
    """All conversation threads for a user, newest first.

    History tab calls this. Pure pass-through to the repo today; lives
    in the service layer so the cap rule and any future filtering
    (search, by-persona) live alongside the write path.
    """
    return await conversation_repo.list_conversations_by_user(db, user_id, channel)


async def get_thread(
    db: AsyncSession, user_id: str, thread_id: str, channel: str = "whatsapp"
) -> Conversation | None:
    """One conversation row by thread_id. None if not found or not owned."""
    return await conversation_repo.get_conversation(db, user_id, thread_id, channel)


async def delete_thread(
    db: AsyncSession, user_id: str, thread_id: str, channel: str = "whatsapp"
) -> bool:
    """Remove the queryable row. Does NOT touch the checkpoint DB."""
    return await conversation_repo.delete_conversation(db, user_id, thread_id, channel)


__all__ = [
    "record_turn",
    "list_threads",
    "get_thread",
    "delete_thread",
    "HISTORY_CAP",
]  # noqa: F401