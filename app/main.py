"""Webhook entrypoint.

OpenWA POSTs events here. We:
  1. Verify the HMAC signature (so spoofed POSTs can't drive our graph).
  2. Pull out the message body and chat id.
  3. Run the LangGraph with that input.
  4. Send the graph's reply back via OpenWA.

This file is the *bridge* between the transport and the graph. It should
stay mechanical — all the interesting logic lives in `graph.py`.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

import httpx

from app.core.config import get_settings
from app.core.deps import get_db

# Load .env from the repo root when running natively (uvicorn app.main:app).
# Docker compose uses `env_file: .env`, so this is a no-op there.
from pathlib import Path
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

settings = get_settings()

log = logging.getLogger("app")
logging.basicConfig(level=settings.LOG_LEVEL,
                    format="%(asctime)s %(levelname)s %(message)s")

# Module-level client; lifespan manages its lifecycle.
_client = None  # OpenWAClient | None

# HMAC secret OpenWA uses to sign outbound webhook payloads. If you don't
# want signature verification (e.g. running locally without a secret set),
# leave this unset and the verification step is skipped.
_WEBHOOK_SECRET = settings.OPENWA_WEBHOOK_SECRET.strip()

# Desktop mode: skip OpenWA if API key not configured
_desktop_mode = not settings.OPENWA_API_KEY or settings.OPENWA_API_KEY.startswith("replace-me")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _client

    # Auto-run pending migrations on startup
    from alembic.config import Config as AlembicConfig
    from alembic import command as alembic_command
    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_command.upgrade(alembic_cfg, "head")
    log.info("Database migrations applied (alembic upgrade head)")

    if _desktop_mode:
        log.info("Running in desktop mode (OpenWA not configured)")
        app.state.graph = None
    else:
        from app.openwa_client import OpenWAClient
        from app.graph import build_graph

        api_key = settings.OPENWA_API_KEY
        if not api_key or api_key.startswith("replace-me"):
            raise RuntimeError(
                "OPENWA_API_KEY is unset or still a placeholder. "
                "Create one in the OpenWA dashboard and put it in .env."
            )
        _client = OpenWAClient()
        log.info("OpenWA client ready: %s session=%s",
                 _client.base_url, _client.session_id)
        if _WEBHOOK_SECRET:
            log.info("Webhook HMAC verification: ON")
        else:
            log.warning("Webhook HMAC verification: OFF (no OPENWA_WEBHOOK_SECRET)")
        # Build the graph on this event loop so its AsyncSqliteSaver
        # background thread lives on the same loop that runs ainvoke().
        app.state.graph = await build_graph()
        log.info("LangGraph compiled (async checkpointer ready)")

    yield

    if _client:
        await _client.aclose()


app = FastAPI(title="whatsapp-bot-langgraph", lifespan=lifespan)

# CORS for Tauri frontend (localhost)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:1420", "http://127.0.0.1:1420"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- API Routers ---
from app.api.auth import router as auth_router
app.include_router(auth_router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Cheap endpoint so we can curl from inside the compose network."""
    return {"status": "ok"}


@app.get("/db-test")
async def db_test(db=Depends(get_db)):
    """Verify the async DB connection works."""
    from sqlalchemy import text
    result = await db.execute(text("SELECT 1"))
    return {"db": "ok", "result": result.scalar()}


@app.post("/debug-webhook")
async def debug_webhook(request: Request) -> dict[str, str]:
    """Temporary endpoint to see what headers OpenWA is sending."""
    headers = dict(request.headers)
    body = await request.body()
    log.info("DEBUG WEBHOOK - Headers: %s", headers)
    log.info("DEBUG WEBHOOK - Body: %s", body[:500])  # First 500 chars
    return {"status": "debug", "headers": str(headers)}


def _verify_signature(raw_body: bytes, signature_header: str | None) -> bool:
    """OpenWA sends `X-OpenWA-Signature: sha256=<hex>`. Compare in constant time."""
    if not _WEBHOOK_SECRET:
        return True  # verification disabled
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(
        _WEBHOOK_SECRET.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    provided = signature_header.split("=", 1)[1]
    return hmac.compare_digest(expected, provided)


# Chat-ID suffixes OpenWA's whatsapp-web.js engine can't reply to.
# We log a single-line warning and skip rather than 500-ing the webhook.
_UNREPLYABLE_SUFFIXES = ("@newsletter", "@broadcast")

@app.post("/webhook")
async def webhook(request: Request) -> dict[str, str]:
    """Receive a single OpenWA event.

    OpenWA's payload (relevant fields):
      {
        "event": "message.received",
        "sessionId": "...",
        "payload": {
          "id": "...",
          "from": "1234567890@c.us",
          "body": "hello",
          "fromMe": false,
          ...
        }
      }
    """
    raw = await request.body()
    if not _verify_signature(raw, request.headers.get("X-OpenWA-Signature")):
        # 401 here will make OpenWA retry with backoff; safer than 200-ignore
        # when we *do* have a secret configured.
        raise HTTPException(status_code=401, detail="bad signature")

    try:
        event: dict[str, Any] = await request.json()
    except Exception:
        # Probe / malformed body — return 200 so OpenWA doesn't retry,
        # but log loudly so we can see what came through.
        log.warning("non-JSON body on /webhook: %r", raw[:200])
        return {"status": "ignored-not-json"}

    if event.get("event") != "message.received":
        # Acknowledge but do nothing — OpenWA expects 2xx on every event.
        return {"status": "ignored"}

    payload = event.get("payload") or event.get("data") or {}
    if payload.get("fromMe"):
        # Without this guard, our reply would be echoed back, generating
        # an infinite loop.
        return {"status": "ignored-our-own-message"}

    body = (payload.get("body") or "").strip()
    chat_id = payload.get("from")
    if not body or not chat_id:
        raise HTTPException(status_code=400, detail="missing body or from")

    # Newsletters and broadcasts can't be replied to (OpenWA returns 400).
    # @lid is newer WhatsApp privacy IDs — OpenWA *may* 500 on these, but
    # we attempt the send anyway and let _handle() catch the error gracefully.
    if chat_id.endswith(("@newsletter", "@broadcast")):
        log.warning("Skipping unreplyable chat_id=%s", chat_id)
        return {"status": "skipped-unreplyable-chat"}

    # Slash-prefix parsing. Two passes because prefixes can combine:
    #   /claude/services hi      -> provider=claude, persona=services
    #   /resume help with CV     -> provider=free,   persona=resume
    #   what do you offer        -> provider=free,   persona unset (classify)
    # Provider prefix must come first; persona prefix can come second.
    provider = "free"
    persona: str | None = None
    text = body.lower().lstrip()

    # /clear wipes the SQLite checkpoint history for this chat. Runs
    # before provider/persona parsing so it short-circuits the rest.
    if text.startswith("/clear"):
        await _clear_thread(request.app, chat_id)
        return {"status": "cleared"}

    # Parse provider prefix first (only one).
    for prefix, name in (("/claude", "claude"), ("/gpt", "gpt")):
        if text.startswith(prefix):
            provider = name
            text = text[len(prefix):].lstrip()
            log.info("routing to provider=%s", name)
            break

    # Then parse persona prefix (only one).
    for prefix, name in (("/resume", "resume"), ("/services", "services"), ("/personal", "personal"), ("/booking", "booking")):
        if text.startswith(prefix):
            persona = name
            text = text[len(prefix):].lstrip()
            log.info("routing to persona=%s", name)
            break

    # Whatever's left of text is what the LLM sees.
    body = text.strip()
    if not body:
        # Slash command without any actual message.
        log.warning("empty body after slash parse (chat=%s)", chat_id)
        return {"status": "empty-after-slash"}

    # ACK fast — OpenWA's webhook timeout is ~10s, and an LLM call can
    # take 2–5s. If we block here, we'd risk hitting the timeout under
    # load and OpenWA would retry, doubling our work. Instead, hand off
    # to a background task and return immediately.
    initial_state = {"message": body, "reply": "", "provider": provider, "persona": persona}
    asyncio.create_task(_handle(request.app, chat_id, initial_state))
    return {"status": "queued"}


async def _clear_thread(app, chat_id: str) -> None:
    """Wipe the SQLite history for this chat and reply with a confirmation.

    Triggered by the `/clear` slash prefix. Calls the AsyncSqliteSaver's
    delete_thread() (a sync method) inside asyncio.to_thread so the event
    loop isn't blocked, then sends a confirmation via OpenWA.

    Errors are logged but never raised — the webhook has already returned
    200 by the time we get here.
    """
    saver = app.state.graph._saver  # stashed by build_graph()
    try:
        await asyncio.to_thread(saver.delete_thread, chat_id)
        log.info("cleared checkpoint history for chat=%s", chat_id)
    except Exception:
        log.exception("failed to clear history for chat=%s", chat_id)
        try:
            await _client.send_text(
                chat_id=chat_id,
                text="Sorry, I couldn't clear the history. Try again or restart the bot.",
            )
        except Exception:
            log.exception("send_text after clear failure also failed for chat=%s", chat_id)
        return

    try:
        await _client.send_text(
            chat_id=chat_id,
            text="Cleared conversation history for this chat.",
        )
    except Exception:
        log.exception("send_text confirmation failed for chat=%s", chat_id)


async def _handle(app, chat_id: str, initial_state: dict) -> None:
    """Background task: run the graph, send the reply. Errors are logged
    but never raised — the webhook already returned 200, so we just
    surface failures to the log for debugging."""
    try:
        # thread_id=chat_id is the key that ties invocations together.
        # The checkpointer uses it to load prior state and persist this
        # turn's state, so the next message from the same chat sees the
        # full conversation history.
        config = {"configurable": {"thread_id": chat_id}}
        result = await app.state.graph.ainvoke(initial_state, config=config)
        reply = (result.get("reply") or "").strip()
        if not reply:
            log.warning("graph returned empty reply for chat=%s", chat_id)
            return

        log.info("chat=%s in=%r out=%r persona=%s provider=%s",
                 chat_id,
                 initial_state.get("message"),
                 reply,
                 result.get("persona", "?"),
                 initial_state.get("provider", "?"))
        try:
            await _client.send_text(chat_id=chat_id, text=reply)
        except httpx.HTTPStatusError as exc:
            body_text = ""
            try:
                body_text = exc.response.text[:200]
            except Exception:
                pass
            log.warning(
                "OpenWA send-text failed (chat_id=%s, status=%d): %s",
                chat_id, exc.response.status_code, body_text,
            )
        except httpx.HTTPError:
            log.exception("OpenWA send-text transport error for chat_id=%s", chat_id)
    except Exception:
        log.exception("Background handler crashed for chat_id=%s", chat_id)


# --- CLI entry point ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=True,
    )