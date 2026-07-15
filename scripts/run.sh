#!/usr/bin/env bash
# Run the LangGraph bot natively (bash — macOS, Linux, Git Bash on Windows).
set -euo pipefail

# Activate venv if it exists.
if [ -f ".venv/Scripts/activate" ]; then
    # Windows venv (Git Bash)
    source .venv/Scripts/activate
elif [ -f ".venv/bin/activate" ]; then
    # Unix venv
    source .venv/bin/activate
else
    echo "No .venv found. Run: python -m venv .venv && source .venv/bin/activate && pip install -e ." >&2
    exit 1
fi

# Confirm deps are installed.
if ! python -c "import openai, langgraph, fastapi" 2>/dev/null; then
    echo "Installing deps..."
    pip install -e .
fi

# Start uvicorn. --reload-exclude ".venv/*" prevents WatchFiles from
# tracking every site-packages file (which causes constant reload churn).
exec uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --reload-exclude ".venv/*"