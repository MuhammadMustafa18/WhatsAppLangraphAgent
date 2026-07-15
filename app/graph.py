"""The reply graph — iteration 2 of the course.

Same shape as iter 1: `START -> node -> END`. Only the node body changed.
`echo` did `state['message'].upper()`. `reply` calls an LLM.

That's the point of LangGraph — the wiring stays the same as the
thinking evolves. Future iterations add more nodes / edges; the call
site in main.py doesn't change.
"""

from langgraph.graph import END, START, StateGraph

from app.llm import chat
from app.state import State

SYSTEM_PROMPT = (
    "You are a helpful WhatsApp assistant. "
    "Reply concisely (1–3 sentences). "
    "Mirror the user's language. "
    "If the user writes in English, reply in English. "
    "If they write in Urdu/Hindi, reply in the same script."
)


def generate(state: State) -> dict:
    """The only node. Asks the LLM to produce a reply for `state['message']`.

    Note the node name (`generate`) and the state field it writes to
    (`reply`) must be different — LangGraph shares one namespace
    between node names and state keys.
    """
    text = chat(SYSTEM_PROMPT, state["message"])
    return {"reply": text}


_builder = StateGraph(State)
_builder.add_node("generate", generate)
_builder.add_edge(START, "generate")
_builder.add_edge("generate", END)

# `graph` is what main.py imports. Keep this name stable.
graph = _builder.compile()