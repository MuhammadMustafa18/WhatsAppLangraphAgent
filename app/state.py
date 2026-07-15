"""State schema for the reply graph.

This is the *only* place state shape is defined. Every iteration of the
course will touch this file — keeping it tiny makes the diff readable.
"""

from typing import TypedDict, Literal


class State(TypedDict):
    """One message in, one reply out. Provider chooses which LLM answers."""

    # The user's raw message body, exactly as OpenWA delivered it.
    message: str

    # What the bot will send back. Filled in by the generate node.
    reply: str

    # Which LLM provider the generate node should call.
    # Set by main.py based on the message prefix:
    #   /claude <msg>  -> "claude"
    #   /gpt    <msg>  -> "gpt"
    #   <msg>          -> "free"   (FreeLLMAPI router, default)
    provider: Literal["claude", "gpt", "free"]


# Provider → human label for logging.
PROVIDER_LABEL = {
    "claude": "Anthropic",
    "gpt": "FreeLLMAPI (gpt)",
    "free": "FreeLLMAPI (auto)",
}