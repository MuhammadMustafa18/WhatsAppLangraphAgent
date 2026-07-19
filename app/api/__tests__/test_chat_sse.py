"""End-to-end test for Phase 23: /chat SSE endpoint for the Tauri UI.

Run:
    PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m app.api.__tests__.test_chat_sse

Verifies:
  - POST /chat requires JWT
  - With a registered provider + persona, the SSE stream yields
    token + done events with the right shapes
  - When the streaming provider yields "alpha", "beta", "gamma",
    the stream emits three token events with those deltas + a
    done event with the full reply
  - The done event includes persona + provider names in the footer
  - The conversation row is created with channel='app'
"""
import asyncio
import uuid
import json

import httpx
from sqlalchemy import select, delete

from app.db.engine import async_session
from app.db.models import Persona, Provider, User, Conversation
from app.core.security import encrypt_value


async def _wipe(user_id: str) -> None:
    async with async_session() as db:
        await db.execute(delete(Conversation).where(Conversation.user_id == user_id))
        await db.execute(delete(Provider).where(Provider.user_id == user_id))
        await db.execute(delete(Persona).where(Conversation.user_id == user_id) if False else delete(Persona).where(Persona.user_id == user_id))
        await db.commit()


async def _seed(user_id: str) -> dict[str, str]:
    async with async_session() as db:
        p = Persona(
            id=str(uuid.uuid4()), user_id=user_id, name="support",
            system_prompt="support prompt", is_active=True,
        )
        prov = Provider(
            id=str(uuid.uuid4()), user_id=user_id, name="chat-test-prov",
            type="openai", api_key=encrypt_value("sk-fake"),
            model="gpt-4o", max_tokens=512, is_default=True,
        )
        db.add_all([p, prov])
        await db.commit()
        return {"persona_id": p.id, "provider_id": prov.id}


class StubProvider:
    """Streams 'alpha', 'beta', 'gamma' one at a time."""

    api_key = "stub"; model = "stub"; base_url = None

    def __init__(self):
        self.tokens_seen = []

    async def chat(self, messages, system=None, max_tokens=1024):
        return "alpha beta gamma"

    async def chat_stream(self, messages, system=None, max_tokens=1024):
        for t in ["alpha ", "beta ", "gamma"]:
            self.tokens_seen.append(t)
            yield t

    async def validate(self): return True
    async def close(self): pass


async def main():
    from app.main import app
    import app.providers.registry as provider_registry

    # Stub the registry
    stub = StubProvider()
    async def fake_get(provider_id):
        return stub
    original_get = provider_registry.get_provider
    provider_registry.get_provider = fake_get  # type: ignore[assignment]

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            # Auth
            r = await client.post("/auth/register", json={
                "username": "mustafa", "password": "password123"
            })
            if r.status_code in (400, 409):
                r = await client.post("/auth/login", json={
                    "username": "mustafa", "password": "password123"
                })
            token = r.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            async with async_session() as db:
                u = (await db.execute(
                    select(User).where(User.username == "mustafa")
                )).scalar_one()
                user_id = u.id

            await _wipe(user_id)
            ids = await _seed(user_id)

            # 1. Unauthenticated → 401/403
            r = await client.post("/chat", json={
                "message": "hello", "persona_id": ids["persona_id"],
            })
            print(f"\n1. unauthenticated /chat: {r.status_code} (expect 401 or 403)")
            assert r.status_code in (401, 403)

            # 2. Authenticated POST → SSE stream
            # httpx streams the response when we use .stream() and read chunks.
            events = []
            async with client.stream(
                "POST", "/chat",
                json={
                    "message": "tell me a story",
                    "persona_id": ids["persona_id"],
                },
                headers=headers,
            ) as resp:
                print(f"\n2. /chat response: {resp.status_code} content-type={resp.headers.get('content-type')}")
                assert resp.status_code == 200
                assert "event-stream" in resp.headers.get("content-type", "")
                # Parse SSE: lines starting with "event:" give us the event name,
                # "data:" gives us the JSON payload.
                cur_event = None
                async for line in resp.aiter_lines():
                    line = line.rstrip("\r")
                    if line.startswith("event:"):
                        cur_event = line[len("event:"):].strip()
                    elif line.startswith("data:"):
                        payload = line[len("data:"):].strip()
                        if cur_event and payload:
                            try:
                                decoded = json.loads(payload)
                            except json.JSONDecodeError:
                                continue
                            events.append((cur_event, decoded))
                            cur_event = None

            print(f"   parsed {len(events)} events:")
            for ev_type, payload in events:
                print(f"     {ev_type}: {payload}")

            # Expect: 3 token events + 1 done event
            assert len(events) == 4, f"expected 4 events, got {len(events)}: {events}"

            tokens = [p["delta"] for (t, p) in events if t == "token"]
            print(f"\n3. tokens seen: {tokens}")
            assert tokens == ["alpha ", "beta ", "gamma"], f"got {tokens}"

            done_events = [(t, p) for (t, p) in events if t == "done"]
            assert len(done_events) == 1
            done_type, done_payload = done_events[0]
            print(f"4. done payload: {done_payload}")
            assert done_payload["reply"] == "alpha beta gamma"
            assert done_payload["persona"] == "support"
            assert done_payload["provider"] == "chat-test-prov"

            # 5. Conversation row was recorded with channel='app'
            async with async_session() as db:
                conv_row = (await db.execute(
                    select(Conversation).where(
                        Conversation.user_id == user_id,
                        Conversation.thread_id == "in-app-default",
                        Conversation.channel == "app",
                    )
                )).scalar_one_or_none()
            print(f"5. conversation row created? {conv_row is not None}")
            assert conv_row is not None
            assert len(conv_row.messages) == 2
            assert conv_row.messages[0] == {"role": "user", "content": "tell me a story"}
            assert conv_row.messages[1] == {"role": "assistant", "content": "alpha beta gamma"}

            await _wipe(user_id)
            print("\nPhase 23 /chat SSE OK")

    finally:
        provider_registry.get_provider = original_get  # type: ignore[assignment]


asyncio.run(main())