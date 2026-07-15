"""State schema for the persona-aware reply graph.

This is the *only* place state shape is defined. Every iteration of the
course will touch this file — keeping it tiny makes the diff readable.
"""

from typing import TypedDict, Literal


# Allowed persona values. Add new personas here and in app/personas.py.
Persona = Literal["resume", "services", "personal"]


class State(TypedDict, total=False):
    """One message in, one reply out. Persona chooses the system prompt.

    `total=False` means fields are optional. The graph fills them in:
      - main.py sets `message`, `provider`, and `persona` (only if slash
        prefix present — otherwise persona is left unset for classify
        to fill).
      - classify fills `persona` if it wasn't already set.
      - generate fills `reply`.
    """

    # The user's message body, with any slash prefix already stripped.
    message: str

    # What the bot will send back. Filled in by the generate node.
    reply: str

    # Which persona's content grounds the response.
    # Set by main.py if a slash prefix was given (/resume, /services, /personal);
    # otherwise set by the classify node via LLM.
    persona: Persona

    # Which LLM provider the generate node should call.
    # Set by main.py based on the message prefix:
    #   /claude <msg>            -> "claude"
    #   /gpt    <msg>            -> "gpt"
    #   <msg>                    -> "free"   (FreeLLMAPI router, default)
    provider: Literal["claude", "gpt", "free"]


# Provider → human label for logging.
PROVIDER_LABEL = {
    "claude": "Anthropic",
    "gpt": "FreeLLMAPI (gpt)",
    "free": "FreeLLMAPI (auto)",
}
