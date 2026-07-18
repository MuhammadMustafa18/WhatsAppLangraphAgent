"""Provider DTOs — request/response shapes for /providers endpoints.

These are the HTTP contract. Separate from the ORM model (app/db/models.py
Provider) because:
  - The DB row carries an encrypted api_key; we never want to leak the
    real ciphertext to clients. Response masks it as 'sk-...last4'.
  - Create / Update accept fields the client owns; id/user_id/created_at
    are server-managed.
  - Validation rules (max_tokens range, type enum, etc.) belong at the
    wire boundary, not on the ORM model.

The service layer (Phase 18) is responsible for converting these to and
from ORM rows. Repos don't see DTOs — they take already-encrypted bytes.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

ProviderType = Literal["openai", "anthropic", "custom"]


class ProviderCreate(BaseModel):
    """Body for POST /providers."""

    name: str = Field(..., min_length=1, max_length=100, examples=["my-gpt4"])
    type: ProviderType = Field(..., examples=["openai"])
    base_url: str | None = Field(
        default=None,
        max_length=500,
        examples=["http://127.0.0.1:31415/v1"],
        description="Required for type=custom; ignored for openai/anthropic.",
    )
    api_key: str = Field(..., min_length=1, max_length=500, examples=["sk-..."])
    model: str = Field(..., min_length=1, max_length=100, examples=["gpt-4o"])
    max_tokens: int = Field(default=1024, ge=1, le=32000)

    @model_validator(mode="after")
    def base_url_required_for_custom(self) -> "ProviderCreate":
        # model_validator runs after every field is set, so we can see
        # both `type` and `base_url` reliably. field_validator can't do
        # this cross-field check in Pydantic v2.
        if self.type == "custom" and not self.base_url:
            raise ValueError("base_url is required when type='custom'")
        return self


class ProviderUpdate(BaseModel):
    """Body for PUT /providers/{id}. All fields optional — only set ones update."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    type: ProviderType | None = None
    base_url: str | None = Field(default=None, max_length=500)
    api_key: str | None = Field(default=None, min_length=1, max_length=500)
    model: str | None = Field(default=None, min_length=1, max_length=100)
    max_tokens: int | None = Field(default=None, ge=1, le=32000)
    is_default: bool | None = None


class ProviderResponse(BaseModel):
    """Shape returned by GET /providers, POST /providers, PUT /providers/{id}.

    api_key is masked — clients never see the real (encrypted) value once
    it's stored. The full key is returned ONCE on POST /providers response,
    via ProviderCreateResponse below.
    """

    id: str
    name: str
    type: ProviderType
    base_url: str | None
    api_key_masked: str  # e.g. "sk-...abc123" — last 4 chars of plaintext
    model: str
    max_tokens: int
    is_default: bool
    created_at: datetime


class ProviderCreateResponse(ProviderResponse):
    """Returned only on POST. Includes the plaintext api_key exactly once so
    the user can save it. Subsequent GETs/PUTs return the masked form."""

    api_key_plain: str