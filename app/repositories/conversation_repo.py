"""Conversation repository — DB queries for the conversations table.

Pure CRUD against the ORM. No history capping here — that belongs in
the service layer because it's a business rule (50 turns), not a
storage concern. Repo just stores whatever messages list it's given.

Functions follow the same pattern as provider_repo.py / persona_repo.py:
take a session, return ORM rows, commit where appropriate.
"""

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Conversation


async def get_conversation(
    db: AsyncSession, user_id: str, thread_id: str, channel: str = "whatsapp"
) -> Conversation | None:
    """Look up a conversation by (user_id, thread_id, channel)."""
    result = await db.execute(
        select(Conversation).where(
            Conversation.user_id == user_id,
            Conversation.thread_id == thread_id,
            Conversation.channel == channel,
        )
    )
    return result.scalar_one_or_none()


async def list_conversations_by_user(
    db: AsyncSession, user_id: str, channel: str | None = None
) -> list[Conversation]:
    """All conversations for a user, most-recent first.

    If channel is provided, filters to just that channel. The History
    tab in the UI uses this to show "WhatsApp chats" vs "App chats".
    """
    stmt = select(Conversation).where(Conversation.user_id == user_id)
    if channel:
        stmt = stmt.where(Conversation.channel == channel)
    stmt = stmt.order_by(Conversation.last_message_at.desc())
    return list((await db.execute(stmt)).scalars())


async def upsert_conversation(
    db: AsyncSession,
    user_id: str,
    thread_id: str,
    messages: list[dict],
    persona_id: str | None = None,
    channel: str = "whatsapp",
) -> Conversation:
    """Insert or replace the conversation row.

    The service layer is responsible for capping messages at 50 turns
    before calling this. Repo just persists what's given.
    Returns the refreshed row.
    """
    existing = await get_conversation(db, user_id, thread_id, channel)
    if existing is None:
        conv = Conversation(
            user_id=user_id,
            thread_id=thread_id,
            channel=channel,
            persona_id=persona_id,
            messages=list(messages),
        )
        db.add(conv)
    else:
        # Update in place. Refresh messages, persona_id, last_message_at.
        await db.execute(
            update(Conversation)
            .where(Conversation.id == existing.id)
            .values(
                messages=list(messages),
                persona_id=persona_id,
                # last_message_at uses DB now() via server_default; we
                # don't need to set it explicitly, but doing so avoids
                # a round-trip to fetch the updated value back.
            )
        )
    await db.commit()
    # Re-query to get the refreshed row with updated_at + last_message_at.
    return await get_conversation(db, user_id, thread_id, channel)


async def delete_conversation(
    db: AsyncSession, user_id: str, thread_id: str, channel: str = "whatsapp"
) -> bool:
    """Delete a conversation row. Returns True if a row was deleted.

    Note: this only deletes the queryable mirror. The checkpointer
    (data/checkpoints.sqlite) keeps the full state unless main.py's
    /clear command is also used.
    """
    existing = await get_conversation(db, user_id, thread_id, channel)
    if existing is None:
        return False
    await db.delete(existing)
    await db.commit()
    return True