# whatsapp-bot-langgraph

A teaching repo for a LangGraph course. We build a WhatsApp-backed bot in
small iterations; each iteration fits in a 5–10 minute explanation.

**Iteration 1 (this one):** OpenWA delivers a message → LangGraph echoes it
uppercased → OpenWA sends it back. One node. One edge. That's it.

## Architecture

```
   WhatsApp user
        ↓ (text message)
   OpenWA gateway  (Docker container, port 2785)
        ↓ (POST to webhook URL)
   ngrok tunnel  (native process, exposes our local app)
        ↓ (forwards to localhost:8000)
   FastAPI + LangGraph app  (native Python, port 8000)
        ↓ (send-text via REST)
   OpenWA gateway
        ↓
   WhatsApp user
```

Three processes — one in Docker, two native. Each is started and stopped
independently, which makes classroom debugging easier.

## Fast path (15 min setup)

```bash
# 1. Configure env
cp .env.example .env
# Edit .env: paste your OPENWA_API_KEY, NGROK_AUTHTOKEN, etc.

# 2. Start OpenWA (Docker)
docker compose up -d openwa
# Dashboard: http://localhost:2785

# 3. Set up the Python venv
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux
pip install -e .

# 4. In OpenWA dashboard:
#    - Create a session (e.g. "langgraph-bot")
#    - Start it, scan the QR with your phone
#    - Add a webhook:
#         URL:    <ngrok URL from step 5>/webhook
#         Events: message.received
#         Secret: matches OPENWA_WEBHOOK_SECRET in .env
#         Active: on

# 5. In a separate terminal, start ngrok:
ngrok http 8000
# Copy the Forwarding URL (e.g. https://abc-xyz.ngrok-free.dev)

# 6. In another terminal, start the app:
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# Look for: "OpenWA client ready" + "Webhook HMAC verification: ON"

# 7. Send "hello" from your phone → receive "HELLO" back.
```

## What to read first

The whole iteration in five files, ~120 lines of code total:

- `app/state.py` — the data shape (4 lines of code, plus comments)
- `app/graph.py` — the entire LangGraph (one node, `START -> echo -> END`)
- `app/main.py` — webhook bridge, glue + signature verification
- `app/openwa_client.py` — outbound HTTP client (resolves session name → UUID)
- `app/__init__.py` — empty, just makes it a package

## Concepts introduced

- `StateGraph`, `START`, `END`, single node, `add_edge`
- `invoke` / `ainvoke` to run the graph
- Partial state returns from a node (return only what changed)
- The shape of state as a `TypedDict`

## Known limitations (will fix in later iterations)

- Outbound to `@lid` chat IDs is skipped — OpenWA's `whatsapp-web.js` engine
  can't translate these to a phone number to send to. We'll switch engines
  (Baileys) in a later iteration.
- No conversation memory — every message is independent.
- No LLM — the echo is a hard-coded transform.

## What's next

Iteration 2 will add a second node that classifies intent (using the local
LLM proxy). The state schema is already ready for it. Nothing else changes.