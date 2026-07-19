"""State schema for the persona-aware, memory-enabled reply graph.

This is the *only* place state shape is defined. Every iteration of the
course will touch this file — keeping it tiny makes the diff readable.

Phase 21a adds `persona_id` and `provider_id` (UUID strings) alongside
the legacy literal fields. The graph will eventually resolve the IDs to
Persona/Provider rows at runtime; for now they coexist with the literal
fields so nothing breaks during the migration.
"""

from typing import Any, TypedDict, Literal


# Allowed persona values. Add new personas here and in app/personas.py.
Persona = Literal["resume", "services", "personal", "booking"]


# A single message in the conversation. We use plain dicts (not
# LangChain's BaseMessage) so the schema stays stdlib-only.
ChatMessage = dict[str, Any]  # {"role": "user"|"assistant", "content": str}


class State(TypedDict, total=False):
    """One message in, one reply out. Persona picks the prompt. Memory
    stores the conversation history.

    `total=False` means fields are optional. The graph fills them in:
      - main.py sets `message`, `provider`, and `persona` (only if slash
        prefix present — otherwise persona is left unset for classify
        to fill).
      - classify fills `persona` if it wasn't already set.
      - generate fills `reply` and appends to `messages`.
      - the checkpointer persists the full state between invocations,
        keyed by `thread_id` (which is the chat_id in main.py).

    Phase 21a: `persona_id` and `provider_id` are the new source of
    truth — they reference rows in the personas / providers tables. The
    legacy literal fields above (`persona`, `provider`) remain so older
    invocations and the slash-prefix flow in main.py still work during
    the migration. Once Phase 21e lands, the webhook will set the IDs
    and the literal fields will be derived downstream.
    """

    # The user's message body, with any slash prefix already stripped.
    message: str

    # What the bot will send back. Filled in by the generate node.
    reply: str

    # Full conversation history. The checkpointer persists this across
    # invocations within the same thread. We append user messages and
    # assistant replies; we never shrink (caller can summarize later
    # if context grows too large).
    messages: list[ChatMessage]

    # Which persona's content grounds the response.
    persona: Persona

    # Which LLM provider the generate node should call.
    provider: Literal["claude", "gpt", "free"]

    # UUID of the Persona row to use. Set by the webhook when the user
    # picks a persona via slash prefix (Phase 21e). The graph resolves
    # this to a Persona ORM row at runtime and pulls system_prompt +
    # knowledge_base from there.
    persona_id: str

    # UUID of the Provider row to use. Same story: set by the webhook
    # from the slash prefix, resolved to a Provider row at runtime. The
    # resolved provider's decrypted credentials go to the LLM call.
    provider_id: str


# Provider → human label for logging.
PROVIDER_LABEL = {
    "claude": "Anthropic",
    "gpt": "FreeLLMAPI (gpt)",
    "free": "FreeLLMAPI (auto)",
}
