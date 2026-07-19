"""ORM models — table definitions only.

Each class = one database table. No queries, no business logic.
Phase 4: User table. Phase 11: Provider table. Phase 19: Persona table.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.sqlite import JSON as SQLiteJSON
from sqlalchemy.types import JSON
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class all models inherit from. Tells SQLAlchemy these are ORM models."""
    pass


def generate_uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(128), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class Provider(Base):
    """LLM provider configuration owned by one user.

    Stored credentials let the desktop app talk to whatever LLM the user
    chooses — OpenAI, Anthropic, or any OpenAI-compatible endpoint (LM
    Studio, Ollama, vLLM, etc.).

    `api_key` is stored as plaintext in Phase 11. Phase 12 swaps to Fernet
    encryption on write + decryption on read; existing rows will be
    migrated in place.
    """

    __tablename__ = "providers"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(100), nullable=False)
    type = Column(String(20), nullable=False)  # "openai" | "anthropic" | "custom"
    base_url = Column(String(500), nullable=True)  # for OpenAI-compatible endpoints
    api_key = Column(String(2000), nullable=False)  # Fernet-encrypted at rest (Phase 12)
    model = Column(String(100), nullable=False)
    max_tokens = Column(
        Integer, nullable=False, default=1024, server_default=text("1024")
    )
    is_default = Column(
        Boolean, nullable=False, default=False, server_default=text("0")
    )
    created_at = Column(
        DateTime, nullable=False, default=utcnow, server_default=text("CURRENT_TIMESTAMP")
    )

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_providers_user_name"),
    )


class Persona(Base):
    """A prompt + optional model override that drives chat behavior.

    A persona is the 'who is talking' configuration: a system prompt, an
    optional knowledge base, and an optional model_override pointing at one
    of the user's Provider rows. When model_override is NULL, the chat
    layer falls back to the user's default Provider.

    Each persona is owned by one user via FK with ON DELETE CASCADE, and
    `model_override` is FK to providers so deleting a provider cascades
    NULL into persona rows (rather than blocking the delete or orphaning).
    """

    __tablename__ = "personas"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(100), nullable=False)
    system_prompt = Column(Text, nullable=False)
    knowledge_base = Column(Text, nullable=True)
    model_override = Column(
        String(36),
        ForeignKey("providers.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_active = Column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )
    created_at = Column(
        DateTime, nullable=False, default=utcnow, server_default=text("CURRENT_TIMESTAMP")
    )

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_personas_user_name"),
    )


class Conversation(Base):
    """Queryable conversation history for one thread.

    The checkpointer (data/checkpoints.sqlite) is the source of truth
    for full graph state across all turns. This table is a queryable
    mirror: one row per thread with the recent message history as JSON,
    so the UI's History tab can list threads and show recent messages
    with a plain SQL query.

    Phase 22 schema:
      - id (UUID PK)
      - user_id (FK -> users.id, ON DELETE CASCADE)
      - thread_id (str) — same key as the checkpointer (chat_id for
        WhatsApp, a generated id for the in-app Chat Preview)
      - channel ('whatsapp' | 'app' | 'webhook') — source of the
        inbound messages. Phase 22 uses a string; Phase 28 (Connections)
        will replace this with a real FK to the future connections table
        via a follow-up migration. Until then, the string is the
        source of truth for grouping in the UI.
      - persona_id (FK -> personas.id, ON DELETE SET NULL) — the persona
        that the last turn resolved to. Nullable so conversations from
        when a persona was deleted still appear in history.
      - messages (JSON) — list of {role, content} pairs, capped at
        50 most-recent turns by the service layer.
      - last_message_at (DateTime) — convenience for "recent threads"
        ORDER BY queries.
      - created_at, updated_at

    `messages` uses JSON type which on SQLite becomes TEXT under the
    hood. Future-proofing: switching to Postgres later needs no schema
    change since JSON is native there.
    """

    __tablename__ = "conversations"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    thread_id = Column(String(200), nullable=False, index=True)
    channel = Column(String(20), nullable=False, default="whatsapp", server_default=text("'whatsapp'"))
    persona_id = Column(
        String(36),
        ForeignKey("personas.id", ondelete="SET NULL"),
        nullable=True,
    )
    messages = Column(JSON, nullable=False, default=list, server_default=text("'[]'"))
    last_message_at = Column(
        DateTime, nullable=False, default=utcnow, server_default=text("CURRENT_TIMESTAMP")
    )
    created_at = Column(
        DateTime, nullable=False, default=utcnow, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at = Column(
        DateTime, nullable=False, default=utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=utcnow,
    )

    __table_args__ = (
        # One row per (user_id, thread_id, channel). Same thread_id
        # across channels (e.g. /chat vs WhatsApp) makes a separate row.
        UniqueConstraint("user_id", "thread_id", "channel", name="uq_conversations_thread"),
    )

