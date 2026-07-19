"""Chat DTOs — request/response shapes for /chat.

Phase 23 contract:
  POST /chat
    body:   ChatRequest (message, persona_id?, provider_id?)
    stream: Server-Sent Events
              data: {"type":"token", "delta":"..."}    per token
              data: {"type":"done", "reply":"...",     at end
                     "persona":"...", "provider":"..."}

The caller can omit persona_id / provider_id and the chat layer
falls back to defaults via _resolve_persona + _resolve_provider
(matching generate's behavior, Phase 21c).

Auth: same JWT as the rest of the API. Phase 23 doesn't introduce
a new auth path.
"""


from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Body for POST /chat."""

    message: str = Field(..., min_length=1, max_length=10000)
    # Optional: explicit IDs from the UI when the user picks a persona
    # or provider. If absent, the chat service falls back to defaults
    # (first active persona, user's default provider).
    persona_id: str | None = Field(default=None, max_length=36)
    provider_id: str | None = Field(default=None, max_length=36)