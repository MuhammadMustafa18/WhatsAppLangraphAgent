"""Webhook entrypoint.

The Baileys sidecar (standalone binary, spawned by Tauri) forwards
incoming WhatsApp messages to /webhook over localhost. We:
  1. Pull out the message body and chat id.
  2. Resolve the user_id from the DB (single-user install: first user
     wins — Tauri app is one-user, per the Phase 21 plan).
  3. Parse slash prefixes into persona_id + provider_id UUIDs by
     matching against the user's Persona / Provider rows by name.
  4. Run the LangGraph with that state + a config carrying user_id and
     thread_id, so the graph's classify + generate can resolve from
     the DB.
  5. Send the graph's reply back via the Baileys sidecar.

This file is the *bridge* between the transport and the graph. It
should stay mechanical — all the interesting logic lives in `graph.py`.
"""

from __future__ import annotations

import asyncio
import os
import sys
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

import httpx
import structlog

from app.core.config import get_settings
from app.core.deps import get_db
from app.core.logging import configure_logging, get_logger, RequestContextMiddleware, log_buffer
from app.db.engine import async_session
from app.db.models import Persona as PersonaRow, Provider as ProviderRow, User
from app.graph import build_graph
from app.repositories import persona_repo, provider_repo

# Load .env from the repo root when running natively (uvicorn app.main:app).
# Docker compose uses `env_file: .env`, so this is a no-op there.
from pathlib import Path
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

settings = get_settings()
configure_logging()

log = get_logger("app")

# Module-level client; lifespan manages its lifecycle.
_client = None  # BaileysClient | None

# Desktop mode — Baileys sidecar is always available when Tauri is running,
# so the graph is always built. The sidecar forwards incoming WhatsApp
# messages to /webhook over localhost (no internet path, no HMAC needed).

# Single-user install: cache the resolved user_id after the first
# webhook hit. Lookup is once per process; Tauri app is one-user.
_cached_user_id: str | None = None


async def _get_single_user_id() -> str | None:
    """Return the id of the single user this install serves.

    The Tauri app is single-user per your design (Phase 21 plan,
    decisions confirmed): one login, one set of personas/providers,
    one WhatsApp gateway. The first user in the DB wins. If no users
    exist (fresh install before signup), returns None and the webhook
    falls back to the legacy _legacy_generate path — which doesn't
    need a user_id.
    """
    global _cached_user_id
    if _cached_user_id is not None:
        return _cached_user_id
    async with async_session() as db:
        u = (await db.execute(select(User).limit(1))).scalar_one_or_none()
        if u is None:
            return None
        _cached_user_id = u.id
        log.info("webhook user resolved", user_id=u.id, username=u.username)
        return _cached_user_id


async def _parse_slash_prefixes(
    user_id: str,
    text: str,
) -> tuple[str | None, str | None, str | None, str]:
    """Parse slash prefixes from `text` for the named user.

    Returns (persona_id, provider_id, persona_literal, body) where:
      - persona_id / provider_id are UUIDs of rows in the user's DB
        tables, looked up by name (case-insensitive).
      - persona_literal is the legacy string ("booking") that gates
        the booking-stub short-circuit in graph.py. It's only set
        when /booking is matched AND the user has a row named that.
      - body is `text` with the matched prefixes stripped.

    If no prefix matches, returns (None, None, None, text).
    """
    persona_id: str | None = None
    provider_id: str | None = None
    persona_literal: str | None = None
    body = text

    lower = body.lower()

    # Provider prefix — first match wins.
    if _starts_with_prefix_word(lower, "/claude"):
        async with async_session() as db:
            provider_id = await _find_provider_by_name(db, user_id, "claude")
        body = body[len("/claude"):].lstrip()
        lower = body.lower()
    elif _starts_with_prefix_word(lower, "/gpt"):
        async with async_session() as db:
            provider_id = await _find_provider_by_name(db, user_id, "gpt")
        body = body[len("/gpt"):].lstrip()
        lower = body.lower()

    # Persona prefix — first match wins.
    for prefix, name in (
        ("/resume", "resume"),
        ("/services", "services"),
        ("/personal", "personal"),
        ("/booking", "booking"),
    ):
        if _starts_with_prefix_word(lower, prefix):
            async with async_session() as db:
                pid = await _find_persona_by_name(db, user_id, name)
            if pid:
                persona_id = pid
                if name == "booking":
                    # Keep the legacy literal so the graph's router
                    # still routes booking to booking_stub. 22+ will
                    # replace this with name-from-resolved-row.
                    persona_literal = "booking"
            else:
                log.warning("slash_prefix_no_persona", prefix=name, user_id=user_id)
            body = body[len(prefix):].lstrip()
            break

    return persona_id, provider_id, persona_literal, body


def _starts_with_prefix_word(text: str, prefix: str) -> bool:
    """True if text starts with prefix followed by a word boundary.

    Without this, '/claude2' would match '/claude' — a real bug in the
    pre-21e parser. Word boundary = end of string OR non-alphanumeric
    next char (whitespace, slash, punctuation).
    """
    if not text.startswith(prefix):
        return False
    if len(text) == len(prefix):
        return True
    next_char = text[len(prefix)]
    return not next_char.isalnum()


async def _find_persona_by_name(db, user_id: str, name: str) -> str | None:
    """Match a user persona by exact (case-insensitive) name. None if absent."""
    rows = await persona_repo.list_personas_by_user(db, user_id)
    for r in rows:
        if r.name.lower() == name.lower():
            return r.id
    return None


async def _find_provider_by_name(db, user_id: str, name: str) -> str | None:
    """Match a user provider by exact (case-insensitive) name. None if absent."""
    rows = await provider_repo.list_providers_by_user(db, user_id)
    for r in rows:
        if r.name.lower() == name.lower():
            return r.id
    return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _client

    # NOTE: alembic auto-migration DISABLED. On Windows + aiosqlite the
    # sync alembic command inside the lifespan's event loop hangs in
    # cleanup (after migrations finish, before the next log line).
    # Workaround: run `alembic upgrade head` manually before starting
    # uvicorn. The schema is stable so this is a one-time thing per
    # dev session. See git log for the failed attempts.

    from app.baileys_client import BaileysClient
    log.info("lifespan_baileys_connecting")
    _client = BaileysClient(base_url=settings.BAILEYS_SIDECAR_URL)
    log.info("lifespan_baileys_ready", url=_client.base_url)

    log.info("lifespan_building_graph")
    app.state.graph = await build_graph()
    log.info("lifespan_graph_ready")

    yield

    if _client:
        await _client.aclose()


app = FastAPI(title="whatsapp-bot-langgraph", lifespan=lifespan)

# Request-id injected into every log line
app.add_middleware(RequestContextMiddleware)

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
from app.api.providers import router as providers_router
from app.api.personas import router as personas_router
app.include_router(auth_router)
app.include_router(providers_router)
app.include_router(personas_router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Cheap endpoint so we can curl from inside the compose network."""
    return {"status": "ok"}


@app.get("/logs")
async def get_logs(lines: int = 100) -> dict[str, Any]:
    """Return recent log lines from the in-memory buffer."""
    return {"lines": list(log_buffer)[-lines:]}


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
    log.info("debug_webhook_headers", headers=headers)
    log.info("debug_webhook_body_preview", body=body[:500])
    return {"status": "debug", "headers": str(headers)}


def _verify_signature(_raw_body: bytes, _signature_header: str | None) -> bool:
    """HMAC verification is disabled — messages come from the local Baileys
    sidecar over localhost, not from OpenWA over the internet. If you need
    verification (e.g. exposing /webhook to a remote service), re-enable
    with a shared secret."""
    return True


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
        log.warning("non_json_body", body_preview=raw[:200])
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
        log.warning("skipping_unreplyable_chat", chat_id=chat_id)
        return {"status": "skipped-unreplyable-chat"}

    # Resolve the single user this install serves. Returns None on a
    # fresh install before signup; in that case the legacy
    # _legacy_generate path runs because user_id is absent from config.
    user_id = await _get_single_user_id()

    # /clear wipes the SQLite checkpoint history for this chat. Runs
    # before prefix parsing so it short-circuits the rest.
    text = body.lower().lstrip()
    if text.startswith("/clear"):
        await _clear_thread(request.app, chat_id)
        return {"status": "cleared"}

    # Slash-prefix parsing. Phase 21e: prefixes now match against
    # DB rows by name, not literals. Returns UUIDs.
    if user_id:
        persona_id, provider_id, persona_literal, body_after = await _parse_slash_prefixes(
            user_id, body,
        )
    else:
        # No user yet — pass through plain text. Legacy _legacy_generate
        # will run because user_id is None.
        persona_id = provider_id = persona_literal = None
        body_after = body

    if persona_id:
        log.info("persona_id_resolved", persona_id=persona_id)
    if provider_id:
        log.info("provider_id_resolved", provider_id=provider_id)

    body = body_after.strip()
    if not body:
        # Slash command without any actual message.
        log.warning("empty_body_after_slash", chat_id=chat_id)
        return {"status": "empty-after-slash"}

    # ACK fast — OpenWA's webhook timeout is ~10s, and an LLM call can
    # take 2–5s. If we block here, we'd risk hitting the timeout under
    # load and OpenWA would retry, doubling our work. Instead, hand off
    # to a background task and return immediately.
    initial_state = {
        "message": body,
        "reply": "",
        # UUIDs of resolved DB rows. classify + generate look these up.
        "persona_id": persona_id,
        "provider_id": provider_id,
        # Legacy literal kept so the router can short-circuit
        # booking to booking_stub without a DB lookup. Empty for
        # everything except /booking.
        "persona": persona_literal,
    }
    asyncio.create_task(_handle(request.app, chat_id, initial_state, user_id))
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
        log.info("checkpoint_history_cleared", chat_id=chat_id)
    except Exception:
        log.exception("failed_to_clear_history", chat_id=chat_id)
        try:
            await _client.send_text(
                chat_id=chat_id,
                text="Sorry, I couldn't clear the history. Try again or restart the bot.",
            )
        except Exception:
            log.exception("send_text_after_clear_failed", chat_id=chat_id)
        return

    try:
        await _client.send_text(
            chat_id=chat_id,
            text="Cleared conversation history for this chat.",
        )
    except Exception:
        log.exception("send_text_confirmation_failed", chat_id=chat_id)


async def _handle(
    app, chat_id: str, initial_state: dict, user_id: str | None,
) -> None:
    """Background task: run the graph, send the reply. Errors are logged
    but never raised — the webhook already returned 200, so we just
    surface failures to the log for debugging."""
    try:
        # thread_id=chat_id is the key that ties invocations together.
        # The checkpointer uses it to load prior state and persist this
        # turn's state, so the next message from the same chat sees the
        # full conversation history.
        # user_id is consumed by classify + generate to resolve persona
        # + provider from the DB at runtime (Phase 21a-e). None means
        # "no user context yet" → graph falls back to _legacy_generate.
        config = {
            "configurable": {
                "thread_id": chat_id,
                "user_id": user_id,
            }
        }
        result = await app.state.graph.ainvoke(initial_state, config=config)
        reply = (result.get("reply") or "").strip()
        if not reply:
            log.warning("empty_reply", chat_id=chat_id)
            return

        log.info("reply_sent",
            chat_id=chat_id,
            in_msg=initial_state.get("message"),
            out_msg=reply,
            persona_id=initial_state.get("persona_id"),
            provider_id=initial_state.get("provider_id"),
        )
        try:
            await _client.send_text(chat_id=chat_id, text=reply)
        except AttributeError:
            # Test mode: _client is None. Don't try to send.
            log.info("no_client_skipping_send")
        except httpx.HTTPStatusError as exc:
            body_text = ""
            try:
                body_text = exc.response.text[:200]
            except Exception:
                pass
            log.warning("send_text_failed",
                chat_id=chat_id, status_code=exc.response.status_code, response_body=body_text,
            )
        except httpx.HTTPError:
            log.exception("send_text_transport_error", chat_id=chat_id)
    except Exception:
        log.exception("background_handler_crashed", chat_id=chat_id)


# --- CLI entry point ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=True,
    )