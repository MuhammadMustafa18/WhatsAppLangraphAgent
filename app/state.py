"""State schema for the echo graph.

This is the *only* place state shape is defined. Every iteration of the
course will touch this file — keeping it tiny makes the diff readable.
"""

from typing import TypedDict


class State(TypedDict):
    """One message in, one reply out. That's the whole model for now."""

    # The user's raw message body, exactly as OpenWA delivered it.
    message: str

    # What the bot will send back. Filled in by the echo node.
    reply: str