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

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.engine import async_session
from app.db.models import Persona as PersonaRow, Provider as ProviderRow
from app.llm import chat as free_chat
from app.personas import BOOKING_STUB_REPLY, DEFAULT_PERSONA, PERSONAS
from app.providers import registry as provider_registry
from app.repositories import persona_repo, provider_repo
from app.state import Persona, State

log = get_logger("graph")

settings = get_settings()

# Where the SQLite checkpointer stores conversation state. One DB for
# the whole app — thread_id inside the DB separates conversations.
_CHECKPOINT_DB = settings.CHECKPOINT_DB


# --- Phase 21b: runtime resolution helpers --------------------------------
#
# Pure functions. No graph wiring yet. Phase 21c will call these from
# `generate` once we've validated them with a script.
#
# Fallback chain (in priority order):
#   1. Explicit state["persona_id"] / state["provider_id"] — set by
#      main.py from a slash prefix in 21e.
#   2. Persona row's `model_override` (for providers) — a persona can
#      pin itself to one provider regardless of the user's default.
#   3. User's default provider / first active persona — used when
#      nothing is set explicitly.
#   4. Hardcoded `personas.py` literals — back-compat fallback so the
#      bot still answers if a user has zero personas / providers.
async def _resolve_persona(
    db: AsyncSession, user_id: str, state: State
) -> PersonaRow:
    """Find the persona this turn should use.

    Order:
      1. state["persona_id"] — explicit ID (post-21e).
      2. First active persona for this user, newest first.
      3. persona named "personal" — match the legacy DEFAULT_PERSONA.

    Raises LookupError if no persona is reachable. The graph has no
    useful behavior without one.
    """
    pid = state.get("persona_id")
    if pid:
        row = await persona_repo.get_persona_by_id(db, pid)
        if row is not None and row.user_id == user_id:
            return row
        log.warning("persona_id_not_found", persona_id=pid, user_id=user_id)

    rows = await persona_repo.list_personas_by_user(db, user_id)
    active = [r for r in rows if r.is_active]
    if active:
        return active[0]

    # Legacy fallback: a persona literally named "personal". Lets a
    # brand-new install boot before any persona row exists.
    for r in rows:
        if r.name == DEFAULT_PERSONA:
            return r

    raise LookupError(
        f"no usable persona for user {user_id!r}: "
        f"create one at /personas"
    )


async def _resolve_provider(
    db: AsyncSession, user_id: str, state: State, persona: PersonaRow
) -> ProviderRow:
    """Find the provider this turn should call.

    Order:
      1. state["provider_id"] — explicit ID (post-21e).
      2. persona.model_override — pinned by the persona itself.
      3. User's is_default provider.
      4. The user's first provider (no preference).

    Raises LookupError if the user has no providers at all.
    """
    pid = state.get("provider_id")
    if pid:
        row = await provider_repo.get_provider_by_id(db, pid)
        if row is not None and row.user_id == user_id:
            return row
        log.warning("provider_id_not_found", provider_id=pid, user_id=user_id)

    if persona.model_override:
        row = await provider_repo.get_provider_by_id(db, persona.model_override)
        if row is not None and row.user_id == user_id:
            return row
        log.warning("model_override_unreachable", persona_id=persona.id, model_override=persona.model_override)

    default = await provider_repo.get_default_provider(db, user_id)
    if default is not None:
        return default

    all_rows = await provider_repo.list_providers_by_user(db, user_id)
    if all_rows:
        return all_rows[0]

    raise LookupError(
        f"no usable provider for user {user_id!r}: "
        f"create one at /providers"
    )


async def classify(state: State, config: dict | None = None) -> dict:
    """Resolve which persona should answer this turn.

    Phase 21d: no LLM call. The user picks personas in the UI; the
    graph looks them up.

    Behavior:
      - If main.py set state["persona_id"] via a slash prefix, pass
        through (the router in _route_after_classify reads it).
      - Otherwise, look up the user's first active persona from the
        DB and set state["persona_id"]. generate() will then resolve
        that id to a Persona row.

    Returns either {} (passthrough) or {"persona_id": <uuid>}.

    Legacy literal field `state["persona"]` is no longer written here.
    generate() doesn't read it. Kept in State schema for backward
    compat with any persisted checkpoints; Phase 22+ may drop it.
    """
    if state.get("persona_id"):
        log.info("persona_id_already_set", persona_id=state["persona_id"])
        return {}

    user_id = (config or {}).get("configurable", {}).get("user_id")
    if not user_id:
        # No user context — can't resolve from DB. Fall back to the
        # legacy literal if main.py set one (slash prefix path), or
        # leave empty so the router dispatches via DEFAULT_PERSONA.
        legacy = state.get("persona")
        if legacy:
            log.info("legacy_persona_no_user_context", persona=legacy)
        return {}

    try:
        async with async_session() as db:
            persona = await _resolve_persona(db, user_id, state)
    except LookupError:
        # No usable persona for this user. Don't crash classify — let
        # generate() raise a clean error with the same message.
        log.warning("no_usable_persona", user_id=user_id)
        return {}

    log.info("resolved_persona", persona=persona.name, user_id=user_id)
    return {"persona_id": persona.id}


def booking_stub(state: State) -> dict:
    """Phase 1 stub for booking requests — no LLM call, no calendar lookup.

    Appends the stub reply to `messages` exactly like `generate` does so
    the checkpointer treats both paths identically. Phase 2+ will replace
    this with a real calendar lookup + owner-approval gate.
    """
    user_msg = state["message"]
    history: list[dict] = state.get("messages", []) or []
    new_history = history + [
        {"role": "user", "content": user_msg},
        {"role": "assistant", "content": BOOKING_STUB_REPLY},
    ]
    return {"reply": BOOKING_STUB_REPLY, "messages": new_history}


async def generate(
    state: State, config: dict | None = None
) -> dict:
    """Answer the message using the persona's content + conversation history.

    Phase 21c: this node no longer reads from the hardcoded PERSONAS
    dict or calls the legacy `_free_multi_turn` / `_claude_multi_turn`
    shims. Instead it:

      1. Pulls user_id from config["configurable"]["user_id"].
      2. Opens its own async DB session (scoped to this node call).
      3. Calls _resolve_persona + _resolve_provider with the session.
      4. Builds the multi-turn messages list from the resolved persona.
      5. Gets a live BaseProvider via provider_registry (cached).
      6. Calls provider.chat(messages, system=...).
      7. Appends both turns to state["messages"] so the checkpointer
         persists the conversation.

    Returns {"reply": text, "messages": new_history}.

    If user_id is missing from config, falls back to the legacy
    PERSONAS dict + a dummy client so unit tests that don't pass config
    still work. (Phase 21e makes config mandatory at the call site.)
    """
    user_id = (config or {}).get("configurable", {}).get("user_id")
    if not user_id:
        # Legacy path: no config means no user context. Use the hardcoded
        # PERSONAS dict and the legacy FreeLLMAPI client. Kept for unit
        # tests that call ainvoke without config. Phase 21e removes this
        # path by making main.py always pass user_id.
        return await _legacy_generate(state)

    user_msg = state["message"]
    history: list[dict] = state.get("messages", []) or []

    async with async_session() as db:
        persona = await _resolve_persona(db, user_id, state)
        provider_row = await _resolve_provider(db, user_id, state, persona)

    system_prompt = persona.system_prompt
    if persona.knowledge_base:
        system_prompt = f"{persona.system_prompt}\n\n{persona.knowledge_base}"

    # Build the message list: prior turns + current user. The system
    # prompt goes via BaseProvider.chat(system=...) so each SDK can
    # route it correctly (Anthropic takes it as a separate arg, OpenAI
    # as a system message — both handled inside the provider).
    msgs: list[dict] = list(history)
    msgs.append({"role": "user", "content": user_msg})

    provider = await provider_registry.get_provider(provider_row.id)
    text = await provider.chat(msgs, system=system_prompt, max_tokens=provider_row.max_tokens)

    new_history = history + [
        {"role": "user", "content": user_msg},
        {"role": "assistant", "content": text},
    ]
    log.info("generated_reply", persona=persona.name, provider=provider_row.name, chars=len(text))
    return {"reply": text, "messages": new_history}


async def _legacy_generate(state: State) -> dict:
    """Pre-Phase-21c path. Reads PERSONAS dict, calls FreeLLMAPI directly.

    Kept so unit tests that don't set up a user + DB can still exercise
    the graph. Phase 21e removes the last caller (main.py webhook).
    """
    persona: Persona = state.get("persona", DEFAULT_PERSONA)
    system_prompt = PERSONAS.get(persona, PERSONAS[DEFAULT_PERSONA])
    user_msg = state["message"]
    history: list[dict] = state.get("messages", []) or []

    msgs = [{"role": "system", "content": system_prompt}]
    msgs.extend(history)
    msgs.append({"role": "user", "content": user_msg})

    from app.llm import _get_client as free_client
    resp = free_client().chat.completions.create(
        model=settings.OPENAI_MODEL, messages=msgs,
    )
    text = (resp.choices[0].message.content or "").strip()

    new_history = history + [
        {"role": "user", "content": user_msg},
        {"role": "assistant", "content": text},
    ]
    return {"reply": text, "messages": new_history}


# Build the graph. Same wiring as iter-4, plus a stub branch for
# booking requests (Phase 1 of the HITL flow — see booking_stub).
_builder = StateGraph(State)
_builder.add_node("classify", classify)
_builder.add_node("generate", generate)
_builder.add_node("booking_stub", booking_stub)


def _resolve_destination(state: State) -> str:
    """Pick the next node from the persona set by classify (or by a slash
    prefix in the input).

    Phase 21d: the routing decision still uses the legacy
    state['persona'] literal because the booking persona is identified
    by the name "booking" — a name match, not a DB lookup. Once 21e
    has populated persona_id, we look up the name from the cached
    persona row. For now, fall back to the literal if no name is
    resolvable from state.
    """
    # Phase 21d transition: the literal state['persona'] still works for
    # main.py slash prefixes (/booking). When classify resolves via DB
    # it sets persona_id but not the legacy literal — the router then
    # falls through to generate(). 21e will close this gap by populating
    # the literal from the resolved row, or by changing the routing to
    # a pre-resolved state key like state['_persona_name'].
    persona_literal = state.get("persona")
    if persona_literal == "booking":
        return "booking_stub"
    return "generate"


def _route_after_classify(state: State) -> str:
    # classify may have set persona_id without setting the legacy
    # literal, in which case we can't tell if it's a "booking" persona
    # without a DB lookup. The router returns "generate" as the safe
    # default — booking personas will get the full LLM reply for now,
    # and the booking-stub behavior is preserved only when the literal
    # "booking" is set explicitly (slash prefix path).
    return _resolve_destination(state)


# Every message re-classifies. classify() short-circuits if main.py set
# persona via a slash prefix, so /booking /resume etc. still skip the
# LLM call. Without this unconditional edge, a stale persona persisted
# from a prior turn would route around classify and amplify any earlier
# misclassification forever (see Phase 1.7 plan).
_builder.add_edge(START, "classify")
_builder.add_conditional_edges("classify", _route_after_classify, {
    "generate": "generate",
    "booking_stub": "booking_stub",
})
_builder.add_edge("generate", END)
_builder.add_edge("booking_stub", END)


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
    # Expose the saver itself so main.py can call delete_thread() for
    # the /clear slash prefix without going through the compiled graph.
    compiled._saver = saver  # type: ignore[attr-defined]
    return compiled