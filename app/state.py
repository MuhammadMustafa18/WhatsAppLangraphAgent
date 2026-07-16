"""State schema for the persona-aware, memory-enabled reply graph.

This is the *only* place state shape is defined. Every iteration of the
course will touch this file — keeping it tiny makes the diff readable.
"""

from typing import Any, TypedDict, Literal


# Allowed persona values. Add new personas here and in app/personas.py.
Persona = Literal["resume", "services", "personal"]


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


# Provider → human label for logging.
PROVIDER_LABEL = {
    "claude": "Anthropic",
    "gpt": "FreeLLMAPI (gpt)",
    "free": "FreeLLMAPI (auto)",
}
