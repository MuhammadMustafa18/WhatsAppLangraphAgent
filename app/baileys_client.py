"""Tiny client for the local Baileys sidecar.

Replaces OpenWAClient. Instead of talking to OpenWA (Docker container),
we send messages to the Baileys sidecar child process on localhost:2786.

The sidecar handles:
  - WhatsApp WebSocket connection
  - QR code generation + pairing
  - Forwarding incoming messages to our /webhook endpoint
  - Persisting the auth session to disk

We only need the outbound path: send a text reply to a chat.
"""

from __future__ import annotations

import logging

import httpx

log = logging.getLogger("app.baileys")


class BaileysClient:
    """HTTP client for the local Baileys sidecar."""

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or "http://127.0.0.1:2786").rstrip("/")
        self._http = httpx.AsyncClient(base_url=self.base_url, timeout=10.0)

    async def send_text(self, chat_id: str, text: str) -> None:
        """POST /send-text — Baileys sidecar sends the message via WhatsApp."""
        resp = await self._http.post(
            "/send-text",
            json={"chatId": chat_id, "text": text},
        )
        resp.raise_for_status()

    async def health(self) -> bool:
        """GET /health — used by Tauri to check if the sidecar is ready."""
        try:
            resp = await self._http.get("/health")
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def status(self) -> dict:
        """GET /status — returns current connection state."""
        try:
            resp = await self._http.get("/status")
            return resp.json() if resp.status_code == 200 else {"status": "unknown"}
        except httpx.HTTPError:
            return {"status": "unreachable"}

    async def aclose(self) -> None:
        await self._http.aclose()
