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
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request

import httpx

from app.graph import graph
from app.openwa_client import OpenWAClient

# Load .env from the repo root when running natively (uvicorn app.main:app).
# Docker compose uses `env_file: .env`, so this is a no-op there.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

log = logging.getLogger("app")
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                    format="%(asctime)s %(levelname)s %(message)s")

# Module-level client; lifespan manages its lifecycle.
_client: OpenWAClient | None = None

# HMAC secret OpenWA uses to sign outbound webhook payloads. If you don't
# want signature verification (e.g. running locally without a secret set),
# leave this unset and the verification step is skipped.
_WEBHOOK_SECRET = os.environ.get("OPENWA_WEBHOOK_SECRET", "").strip()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _client
    api_key = os.environ.get("OPENWA_API_KEY", "")
    if not api_key or api_key.startswith("replace-me"):
        # Fail loudly at boot rather than failing on first inbound POST.
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
    yield
    await _client.aclose()


app = FastAPI(title="whatsapp-bot-langgraph", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    """Cheap endpoint so we can curl from inside the compose network."""
    return {"status": "ok"}


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

    event: dict[str, Any] = await request.json()

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

    # Slash-prefix routing: /claude -> Anthropic, /gpt -> FreeLLMAPI (pinned).
    # Anything else routes through FreeLLMAPI's auto router.
    provider = "free"
    lower = body.lower().lstrip()
    for prefix, name in (("/claude", "claude"), ("/gpt", "gpt")):
        if lower.startswith(prefix):
            provider = name
            body = body[len(prefix):].lstrip()
            log.info("routing to provider=%s", name)
            break

    # ACK fast — OpenWA's webhook timeout is ~10s, and an LLM call can
    # take 2–5s. If we block here, we'd risk hitting the timeout under
    # load and OpenWA would retry, doubling our work. Instead, hand off
    # to a background task and return immediately.
    asyncio.create_task(_handle(chat_id, body, provider))
    return {"status": "queued"}


async def _handle(chat_id: str, body: str, provider: str = "free") -> None:
    """Background task: run the graph, send the reply. Errors are logged
    but never raised — the webhook already returned 200, so we just
    surface failures to the log for debugging."""
    try:
        result = await graph.ainvoke(
            {"message": body, "reply": "", "provider": provider}
        )
        reply = (result.get("reply") or "").strip()
        if not reply:
            log.warning("graph returned empty reply for chat=%s body=%r", chat_id, body[:80])
            return

        log.info("chat=%s in=%r out=%r", chat_id, body, reply)
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