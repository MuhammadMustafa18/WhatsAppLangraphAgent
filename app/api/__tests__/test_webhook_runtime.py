"""End-to-end test for Phase 21e: webhook → graph → reply with DB-resolved ids.

Run:
    PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m app.api.__tests__.test_webhook_runtime

Simulates OpenWA by sending fake payloads to /webhook and asserts the
graph receives the right persona_id + provider_id from main.py's
slash-prefix parser.

The actual graph ainvoke() is stubbed — we just want to confirm the
webhook delivers the right state + config to the graph, not that the
graph itself runs (that's covered by Phase 21b/c/d tests).
"""
import asyncio
import httpx
import uuid
from typing import Any

from sqlalchemy import select, delete

from app.db.engine import async_session
from app.db.models import Persona, Provider, User
from app.core.security import encrypt_value


async def _wipe(user_id: str) -> None:
    async with async_session() as db:
        await db.execute(delete(Provider).where(Provider.user_id == user_id))
        await db.execute(delete(Persona).where(Persona.user_id == user_id))
        await db.commit()


async def _seed(user_id: str) -> dict[str, str]:
    async with async_session() as db:
        personas = {
            "services": Persona(
                id=str(uuid.uuid4()), user_id=user_id, name="services",
                system_prompt="services prompt", is_active=True,
            ),
            "booking": Persona(
                id=str(uuid.uuid4()), user_id=user_id, name="booking",
                system_prompt="booking prompt", is_active=True,
            ),
        }
        providers = {
            "claude": Provider(
                id=str(uuid.uuid4()), user_id=user_id, name="claude",
                type="anthropic", api_key=encrypt_value("sk-fake-ant"),
                model="claude-sonnet-4-5", max_tokens=1024,
                is_default=False,
            ),
            "gpt": Provider(
                id=str(uuid.uuid4()), user_id=user_id, name="gpt",
                type="openai", api_key=encrypt_value("sk-fake-openai"),
                model="gpt-4o", max_tokens=1024,
                is_default=True,
            ),
        }
        db.add_all(list(personas.values()) + list(providers.values()))
        await db.commit()
        return {
            **{f"persona_{k}": v.id for k, v in personas.items()},
            **{f"provider_{k}": v.id for k, v in providers.items()},
        }


class CapturedAinvoke:
    """Stub the graph's ainvoke — captures the call args, returns canned reply."""

    def __init__(self):
        self.last_initial_state: dict | None = None
        self.last_config: dict | None = None
        self.calls = 0

    async def __call__(self, initial_state: dict, config: dict | None = None):
        self.calls += 1
        self.last_initial_state = initial_state
        self.last_config = config
        return {
            "reply": "stub-graph-reply",
            "messages": initial_state.get("messages", []),
            "persona_id": initial_state.get("persona_id"),
        }


async def main():
    from app.main import app
    import app.main as main_mod

    # Reset cached user_id so the test sees a fresh lookup.
    main_mod._cached_user_id = None

    # Stub the graph directly on app.state — simpler than fighting
    # lifespan context. We just need the webhook → ainvoke path.
    captured = CapturedAinvoke()

    class FakeGraph:
        async def ainvoke(self, state, config=None):
            return await captured(state, config)
        _saver = None
        _saver_cm = None
    app.state.graph = FakeGraph()

    # Stub OpenWA so outbound send doesn't try real network.
    main_mod._client = None
    main_mod._WEBHOOK_SECRET = ""

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        # Auth mustafa
        r = await client.post("/auth/register", json={
            "username": "mustafa", "password": "password123"
        })
        if r.status_code in (400, 409):
            r = await client.post("/auth/login", json={
                "username": "mustafa", "password": "password123"
            })
        if r.status_code != 200:
            raise SystemExit(f"auth failed: {r.status_code} {r.text}")

        async with async_session() as db:
            u = (await db.execute(
                select(User).where(User.username == "mustafa")
            )).scalar_one()
            user_id = u.id

        await _wipe(user_id)
        ids = await _seed(user_id)

        def post_webhook(body: str) -> dict[str, Any]:
            return {
                "event": "message.received",
                "payload": {
                    "id": "msg-1",
                    "from": "1234567890@c.us",
                    "body": body,
                    "fromMe": False,
                },
            }

        # ---- Test 1: no slash prefix → no persona_id, default resolves ----
        captured.calls = 0
        r = await client.post("/webhook", json=post_webhook("hello"))
        assert r.status_code == 200, r.text
        await asyncio.sleep(0.2)
        assert captured.calls == 1, f"expected 1 call, got {captured.calls}"
        state = captured.last_initial_state
        print(f"\n1. no prefix → message={state['message']!r}")
        print(f"   persona_id={state['persona_id']}, provider_id={state['provider_id']}")
        assert state["message"] == "hello"
        assert state["persona_id"] is None, "no prefix → no explicit id"
        assert state["provider_id"] is None
        assert state["persona"] is None
        cfg = captured.last_config["configurable"]
        assert cfg["thread_id"] == "1234567890@c.us"
        assert cfg["user_id"] == user_id

        # ---- Test 2: /claude prefix → provider_id, persona_literal unset ----
        captured.calls = 0
        r = await client.post("/webhook", json=post_webhook("/claude what's the weather?"))
        assert r.status_code == 200
        await asyncio.sleep(0.2)
        state = captured.last_initial_state
        print(f"\n2. /claude prefix → message={state['message']!r}")
        print(f"   persona_id={state['persona_id']}, provider_id={state['provider_id']}")
        assert state["message"] == "what's the weather?"
        assert state["provider_id"] == ids["provider_claude"]
        assert state["persona_id"] is None
        assert state["persona"] is None

        # ---- Test 3: /booking prefix → persona_id + persona_literal=booking ----
        captured.calls = 0
        r = await client.post("/webhook", json=post_webhook("/booking please meet tomorrow"))
        assert r.status_code == 200
        await asyncio.sleep(0.2)
        state = captured.last_initial_state
        print(f"\n3. /booking prefix → message={state['message']!r}")
        print(f"   persona_id={state['persona_id']}, persona_literal={state['persona']!r}")
        assert state["message"] == "please meet tomorrow"
        assert state["persona_id"] == ids["persona_booking"]
        assert state["persona"] == "booking", "literal set for booking-stub router"

        # ---- Test 4: /gpt/services prefix → both provider + persona ----
        captured.calls = 0
        r = await client.post("/webhook", json=post_webhook("/gpt/services refund question"))
        assert r.status_code == 200
        await asyncio.sleep(0.2)
        state = captured.last_initial_state
        print(f"\n4. /gpt/services prefix → message={state['message']!r}")
        print(f"   persona_id={state['persona_id']}, provider_id={state['provider_id']}")
        assert state["message"] == "refund question"
        assert state["provider_id"] == ids["provider_gpt"]
        assert state["persona_id"] == ids["persona_services"]
        assert state["persona"] is None

        # ---- Test 5: unknown prefix name → graceful (no id set) ----
        captured.calls = 0
        r = await client.post("/webhook", json=post_webhook("/claude2 something"))
        assert r.status_code == 200
        await asyncio.sleep(0.2)
        state = captured.last_initial_state
        print(f"\n5. unknown prefix /claude2 → message={state['message']!r}")
        print(f"   persona_id={state['persona_id']}, provider_id={state['provider_id']}")
        assert state["message"] == "/claude2 something", "passed through verbatim"

        # ---- Test 6: /clear still works ----
        captured.calls = 0
        r = await client.post("/webhook", json=post_webhook("/clear"))
        assert r.status_code == 200
        await asyncio.sleep(0.2)
        print(f"\n6. /clear → graph not invoked: {captured.calls == 0}")
        assert captured.calls == 0, "/clear should not ainvoke the graph"

        # ---- Test 7: empty body after slash → 200, not graph ----
        captured.calls = 0
        r = await client.post("/webhook", json=post_webhook("/claude"))
        assert r.status_code == 200
        await asyncio.sleep(0.2)
        print(f"\n7. /claude alone → graph not invoked: {captured.calls == 0}")
        assert captured.calls == 0, "empty-after-slash should short-circuit"

        # cleanup
        await _wipe(user_id)
        main_mod._cached_user_id = None
        print("\nPhase 21e webhook → graph runtime OK")


asyncio.run(main())