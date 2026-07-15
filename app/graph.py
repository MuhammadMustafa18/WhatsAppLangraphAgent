"""The persona-aware reply graph — iteration 4 of the course.

Graph shape:
    classify -> generate -> END
        ^
   (skipped if main.py set a persona via slash prefix)

`classify` picks a persona if main.py didn't already set one (i.e. no
slash prefix was given). `generate` looks up the persona's content,
calls the LLM, returns the reply.

This iteration introduces two LangGraph concepts:
  - Multiple nodes chained together (not just one)
  - Conditional routing via add_conditional_edges — the START node
    routes to classify if persona is unset, else directly to generate.
"""

import logging

from langgraph.graph import END, START, StateGraph

from app.anthropic_client import chat as claude_chat
from app.llm import chat as free_chat
from app.personas import CLASSIFY_PROMPT, DEFAULT_PERSONA, PERSONAS
from app.state import Persona, State

log = logging.getLogger("app.graph")

# Model pinned by /gpt — FreeLLMAPI exposes this free OpenAI-style
# endpoint. Swap to whatever you have enabled locally.
_GPT_MODEL = "gpt-oss-120b"

# Model used for the auto-classify LLM call. Cheap + fast; we only need
# a one-word answer.
_CLASSIFY_MODEL = "auto"


def classify(state: State) -> dict:
    """Pick a persona for the message.

    - If main.py already set one (via /resume, /services, /personal),
      just pass through.
    - Otherwise, ask the LLM to pick from {resume, services, personal}.
    - Default to 'personal' if the LLM returns something unexpected.
    """
    existing = state.get("persona")
    if existing:
        log.info("persona already set by slash prefix: %s", existing)
        return {}

    raw = free_chat(
        "You are a routing assistant.",
        CLASSIFY_PROMPT.format(message=state["message"]),
        model=_CLASSIFY_MODEL,
    ).strip().lower()

    if raw in ("resume", "services", "personal"):
        log.info("classify picked persona=%s", raw)
        return {"persona": raw}

    # Model returned something we don't recognize — default.
    log.warning("classify got %r, defaulting to %s", raw, DEFAULT_PERSONA)
    return {"persona": DEFAULT_PERSONA}


def generate(state: State) -> dict:
    """Answer the message using the persona's content as context.

    Provider values (set by main.py based on the message prefix):
      - "claude" -> Anthropic Messages API via the configured proxy
      - "gpt"    -> FreeLLMAPI, pinned to a GPT-style model
      - "free"   -> FreeLLMAPI router (auto-picks the best available)
    """
    persona: Persona = state.get("persona", DEFAULT_PERSONA)
    system_prompt = PERSONAS.get(persona, PERSONAS[DEFAULT_PERSONA])
    user_msg = state["message"]
    provider = state.get("provider", "free")

    if provider == "claude":
        text = claude_chat(system_prompt, user_msg)
    elif provider == "gpt":
        text = free_chat(system_prompt, user_msg, model=_GPT_MODEL)
    else:
        text = free_chat(system_prompt, user_msg)

    return {"reply": text}


_builder = StateGraph(State)
_builder.add_node("classify", classify)
_builder.add_node("generate", generate)


def _route_from_start(state: State) -> str:
    """If main.py set a persona via slash prefix, skip classify.
    Otherwise route through classify so the LLM picks one."""
    return "generate" if state.get("persona") else "classify"


_builder.add_conditional_edges(START, _route_from_start, {
    "classify": "classify",
    "generate": "generate",
})
_builder.add_edge("classify", "generate")
_builder.add_edge("generate", END)

# `graph` is what main.py imports. Keep this name stable.
graph = _builder.compile()
