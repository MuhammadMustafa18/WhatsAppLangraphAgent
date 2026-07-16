"""The persona-aware, memory-enabled reply graph — iteration 5.

Graph shape:
    classify -> generate -> END
        ^
   (skipped if main.py set a persona via slash prefix)

Iteration 5 introduces:
  - Conversation memory via SqliteSaver checkpointer. Each chat_id is
    a thread; the bot remembers prior turns within a thread but not
    across threads.
  - Multi-turn LLM calls. `generate` reads `state["messages"]` (the
    conversation so far), appends the new user message + system prompt,
    calls the LLM, then appends the reply to the same list.
  - thread_id config. main.py passes `{"configurable": {"thread_id":
    chat_id}}` so the checkpointer knows which conversation to load.

State shape (in app/state.py):
    message:   str           # current user message
    messages:  list[dict]    # running conversation history (persisted)
    persona:   "resume"|"services"|"personal"
    provider:  "claude"|"gpt"|"free"
    reply:     str           # this turn's reply
"""

import logging
import os

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph

from app.anthropic_client import chat as claude_chat
from app.llm import chat as free_chat, _get_client as free_client
from app.personas import CLASSIFY_PROMPT, DEFAULT_PERSONA, PERSONAS
from app.state import Persona, State

log = logging.getLogger("app.graph")

# Model pinned by /gpt — FreeLLMAPI exposes this free OpenAI-style
# endpoint. Swap to whatever you have enabled locally.
_GPT_MODEL = "gpt-oss-120b"

# Model used for the auto-classify LLM call. Cheap + fast; we only need
# a one-word answer.
_CLASSIFY_MODEL = "auto"

# Where the SQLite checkpointer stores conversation state. One DB for
# the whole app — thread_id inside the DB separates conversations.
_CHECKPOINT_DB = os.environ.get("CHECKPOINT_DB", "data/checkpoints.sqlite")


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
    """Answer the message using the persona's content + conversation history.

    Builds a multi-turn prompt from `state["messages"]`, calls the LLM,
    and returns the new assistant reply. The reply and the user's input
    are appended to `state["messages"]` so the checkpointer persists the
    full conversation.

    Provider values (set by main.py based on the message prefix):
      - "claude" -> Anthropic Messages API via the configured proxy
      - "gpt"    -> FreeLLMAPI, pinned to a GPT-style model
      - "free"   -> FreeLLMAPI router (auto-picks the best available)
    """
    persona: Persona = state.get("persona", DEFAULT_PERSONA)
    system_prompt = PERSONAS.get(persona, PERSONAS[DEFAULT_PERSONA])
    user_msg = state["message"]
    provider = state.get("provider", "free")
    history: list[dict] = state.get("messages", []) or []

    # Build the full message list: system, prior turns, current user.
    msgs = [{"role": "system", "content": system_prompt}]
    msgs.extend(history)
    msgs.append({"role": "user", "content": user_msg})

    if provider == "claude":
        # Anthropic takes system as a separate arg, not in the messages list.
        text = _claude_multi_turn(system_prompt, history, user_msg)
    elif provider == "gpt":
        text = _free_multi_turn(msgs, model=_GPT_MODEL)
    else:
        text = _free_multi_turn(msgs, model="auto")

    # Append both turns so the next invocation sees them.
    new_history = history + [
        {"role": "user", "content": user_msg},
        {"role": "assistant", "content": text},
    ]
    return {"reply": text, "messages": new_history}


def _free_multi_turn(msgs: list[dict], model: str | None) -> str:
    """OpenAI-style multi-turn call (used for both /free and /gpt)."""
    resp = free_client().chat.completions.create(model=model or "auto", messages=msgs)
    return (resp.choices[0].message.content or "").strip()


def _claude_multi_turn(system: str, history: list[dict], user_msg: str) -> str:
    """Anthropic Messages API: system is a separate arg, no system role in messages."""
    msgs = []
    for m in history:
        # Map our generic role names to Anthropic's. Anthropic only
        # accepts 'user' and 'assistant' in the messages list.
        role = m.get("role")
        if role in ("user", "assistant"):
            msgs.append({"role": role, "content": m["content"]})
    msgs.append({"role": "user", "content": user_msg})

    from app.anthropic_client import _get_client as claude_client
    resp = claude_client().messages.create(
        model=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5"),
        max_tokens=1024,
        system=system,
        messages=msgs,
    )
    parts = []
    for block in resp.content:
        if getattr(block, "type", None) == "text":
            parts.append(block.text)
    return "\n".join(parts).strip() or "(empty response)"


# Build the graph. Same wiring as iter-4.
_builder = StateGraph(State)
_builder.add_node("classify", classify)
_builder.add_node("generate", generate)


def _route_from_start(state: State) -> str:
    return "generate" if state.get("persona") else "classify"


_builder.add_conditional_edges(START, _route_from_start, {
    "classify": "classify",
    "generate": "generate",
})
_builder.add_edge("classify", "generate")
_builder.add_edge("generate", END)


# Compile with AsyncSqliteSaver inside uvicorn's lifespan — the
# checkpointer holds an aiosqlite.Connection whose background thread
# lives on the same event loop that runs the graph. Building it at
# module-import time would create a loop, tear it down, and leave the
# connection dead. main.py's lifespan calls build_graph() once at
# startup and stashes the result on app.state.graph.
import os as _os
_dir = _os.path.dirname(_CHECKPOINT_DB)
if _dir:
    _os.makedirs(_dir, exist_ok=True)

# Module-level handle: the compiled graph (or None until lifespan
# builds it). Tests / scripts that don't go through FastAPI can call
# build_graph() once and assign the result here.
graph = None  # type: ignore[assignment]


async def build_graph():
    """Open the async checkpointer and compile the graph.

    Caller owns the returned object's lifetime — the AsyncSqliteSaver
    inside stays bound to the event loop that compiled it.
    """
    saver_cm = AsyncSqliteSaver.from_conn_string(_CHECKPOINT_DB)
    saver = await saver_cm.__aenter__()
    compiled = _builder.compile(checkpointer=saver)
    # Hold the context manager alive so __aexit__ never runs while
    # the graph is in use.
    compiled._saver_cm = saver_cm  # type: ignore[attr-defined]
    return compiled