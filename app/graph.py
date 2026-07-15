"""The reply graph — iteration 3 (multi-provider).

Same shape as iter 2: `START -> generate -> END`. Only the node body
grew: it now picks an LLM client based on `state['provider']`.

That's still the point of LangGraph — the wiring stays the same as
the thinking evolves. Next iteration will add a second node and a
conditional edge; main.py won't change.
"""

from langgraph.graph import END, START, StateGraph

from app.anthropic_client import chat as claude_chat
from app.llm import chat as free_chat
from app.state import State

SYSTEM_PROMPT = (
    "You are a helpful WhatsApp assistant. "
    "Reply concisely (1–3 sentences). "
    "Mirror the user's language. "
    "If the user writes in English, reply in English. "
    "If they write in Urdu/Hindi, reply in the same script."
)

# Model pinned by /gpt — FreeLLMAPI exposes this free OpenAI-style
# endpoint. Swap to whatever you have enabled locally.
_GPT_MODEL = "gpt-oss-120b"


def generate(state: State) -> dict:
    """The only node. Picks an LLM based on `state['provider']` and
    produces a reply for `state['message']`.

    Provider values (set by main.py based on the message prefix):
      - "claude" → Anthropic Messages API via the configured proxy
      - "gpt"    → FreeLLMAPI, pinned to a GPT-style model
      - "free"   → FreeLLMAPI router (auto-picks the best available)
    """
    user_msg = state["message"]
    provider = state.get("provider", "free")

    if provider == "claude":
        text = claude_chat(SYSTEM_PROMPT, user_msg)
    elif provider == "gpt":
        text = free_chat(SYSTEM_PROMPT, user_msg, model=_GPT_MODEL)
    else:
        text = free_chat(SYSTEM_PROMPT, user_msg)

    return {"reply": text}


_builder = StateGraph(State)
_builder.add_node("generate", generate)
_builder.add_edge(START, "generate")
_builder.add_edge("generate", END)

# `graph` is what main.py imports. Keep this name stable.
graph = _builder.compile()