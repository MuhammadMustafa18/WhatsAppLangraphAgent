"""Tiny client for the OpenWA REST API.

We only need two operations for iteration 1:
  - Send a text reply to a chat.
  - (Later) subscribe to message events — but OpenWA handles that via webhooks,
    so this client is purely *outbound*.

Keep this file boring. If it grows past ~50 lines, that's a smell.
"""

from __future__ import annotations

import logging

import httpx

from app.core.config import get_settings

log = logging.getLogger("app.openwa")


class OpenWAClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        session_id: str | None = None,
    ) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.OPENWA_API_URL).rstrip("/")
        self.api_key = api_key or settings.OPENWA_API_KEY
        # We accept either a session NAME (e.g. "langgraph-bot") or a UUID.
        # If a name is given, we resolve it to its UUID on startup because
        # OpenWA's REST endpoints expect the UUID in the URL path. This was
        # the source of mysterious 400/500 errors in iteration 1.
        requested = session_id or settings.OPENWA_SESSION_ID
        self.session_id = self._resolve_session_id(requested)

        # One client, reused — OpenWA sessions are long-lived.
        self._http = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"X-API-Key": self.api_key},
            timeout=10.0,
        )

    def _resolve_session_id(self, requested: str) -> str:
        """UUIDs pass through unchanged. Names get resolved via /api/sessions."""
        # Looks like a UUID already (8-4-4-4-12 hex pattern).
        if len(requested) == 36 and requested.count("-") == 4:
            return requested

        # Synchronous httpx (we're in __init__, not async yet).
        try:
            with httpx.Client(timeout=10.0) as sync_http:
                r = sync_http.get(
                    f"{self.base_url}/api/sessions",
                    headers={"X-API-Key": self.api_key},
                )
                r.raise_for_status()
                for s in r.json():
                    if s.get("name") == requested:
                        log.info("Resolved session %r -> %s", requested, s["id"])
                        return s["id"]
        except Exception as e:
            log.warning("Session-name resolution failed (%s); using %r as-is",
                        e, requested)

        log.warning("Session %r not found via API; passing it through anyway",
                    requested)
        return requested

    async def send_text(self, chat_id: str, text: str) -> None:
        """POST /api/sessions/{sessionId}/messages/send-text

        `chat_id` comes straight from the inbound webhook payload
        (OpenWA delivers it as `payload.from`).
        """
        resp = await self._http.post(
            f"/api/sessions/{self.session_id}/messages/send-text",
            json={"chatId": chat_id, "text": text},
        )
        resp.raise_for_status()

    async def aclose(self) -> None:
        await self._http.aclose()