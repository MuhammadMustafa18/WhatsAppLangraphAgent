"""ORM models — table definitions only.

Each class = one database table. No queries, no business logic.
Phase 4: User table. More tables added in later phases.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, text
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
    api_key = Column(String(500), nullable=False)
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

