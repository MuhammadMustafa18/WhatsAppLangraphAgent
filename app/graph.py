"""The echo graph — iteration 1 of the course.

Read this file top-to-bottom in 90 seconds:

  1. Define a `State` (lives in state.py).
  2. Write a node function: takes state in, returns a partial state out.
  3. Wire it into a `StateGraph`, compile, done.

Next iteration we will:
  - Add a second node that classifies intent.
  - Add a conditional edge between them.
The only thing that changes is this file. State shape is already ready
for it (see state.py — no changes there either).
"""

from langgraph.graph import END, START, StateGraph

from app.state import State


def echo(state: State) -> dict:
    """The only node. Takes the message, uppercases it, stores reply.

    A node returns a *partial* state dict. LangGraph merges it into the
    full state. We don't return `message` because we're not changing it.
    """
    return {"reply": state["message"].upper()}


# Build the graph: START -> echo -> END. That's it.
_builder = StateGraph(State)
_builder.add_node("echo", echo)
_builder.add_edge(START, "echo")
_builder.add_edge("echo", END)

# `app` is what main.py imports. Keep this name stable — every iteration
# of the course exports a `graph` with the same shape.
graph = _builder.compile()