"""End-to-end test for Phase 22: Conversation model + cap-at-50 service.

Run:
    PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m app.__tests__.test_conversations

Verifies:
  - record_turn creates a row on first call
  - record_turn updates an existing row (no duplicate)
  - cap-at-50 trims older messages; repo keeps the latest N
  - list_threads returns newest first
  - delete_thread removes the row
  - generate() (Phase 22 wiring) writes the row inside the runtime path
"""
import asyncio
import uuid

from sqlalchemy import select, delete

from app.db.engine import async_session
from app.db.models import Conversation, Persona, Provider, User
from app.core.security import encrypt_value


async def _wipe(user_id: str) -> None:
    async with async_session() as db:
        await db.execute(delete(Conversation).where(Conversation.user_id == user_id))
        await db.execute(delete(Provider).where(Provider.user_id == user_id))
        await db.execute(delete(Persona).where(Persona.user_id == user_id))
        await db.commit()


async def _seed(user_id: str) -> dict[str, str]:
    async with async_session() as db:
        p = Persona(
            id=str(uuid.uuid4()), user_id=user_id, name="support",
            system_prompt="support prompt", is_active=True,
        )
        prov = Provider(
            id=str(uuid.uuid4()), user_id=user_id, name="conv-test",
            type="openai", api_key=encrypt_value("sk-fake"),
            model="gpt-4o", max_tokens=512, is_default=True,
        )
        db.add_all([p, prov])
        await db.commit()
        return {"persona_id": p.id, "provider_id": prov.id}


async def main():
    from app.services import conversation_service

    async with async_session() as db:
        u = (await db.execute(
            select(User).where(User.username == "mustafa")
        )).scalar_one_or_none()
        if u is None:
            raise SystemExit("mustafa not registered")
        user_id = u.id

    await _wipe(user_id)
    ids = await _seed(user_id)

    # 1. First record_turn creates a row.
    msgs = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    async with async_session() as db:
        row = await conversation_service.record_turn(
            db, user_id=user_id, thread_id="thread-1",
            messages=msgs, persona_id=ids["persona_id"],
        )
    print(f"\n1. first turn → row id={row.id}, messages={len(row.messages)}")
    assert row.messages == msgs

    # 2. Second record_turn updates in place (no duplicate).
    msgs2 = msgs + [
        {"role": "user", "content": "are you there?"},
        {"role": "assistant", "content": "yes, I'm here"},
    ]
    async with async_session() as db:
        row = await conversation_service.record_turn(
            db, user_id=user_id, thread_id="thread-1",
            messages=msgs2, persona_id=ids["persona_id"],
        )
    async with async_session() as db:
        all_rows = (await db.execute(
            select(Conversation).where(
                Conversation.user_id == user_id,
                Conversation.thread_id == "thread-1",
            )
        )).scalars().all()
    print(f"2. second turn → rows={len(all_rows)}, messages={len(row.messages)}")
    assert len(all_rows) == 1, "no duplicate row"
    assert len(row.messages) == 4

    # 3. Cap-at-50: write 60 messages; service trims to last 50.
    big = [{"role": "user", "content": f"m{i}"} for i in range(30)] + \
          [{"role": "assistant", "content": f"r{i}"} for i in range(30)]
    assert len(big) == 60
    async with async_session() as db:
        row = await conversation_service.record_turn(
            db, user_id=user_id, thread_id="thread-1",
            messages=big, persona_id=ids["persona_id"],
        )
    print(f"3. 60-msg input → stored {len(row.messages)}")
    assert len(row.messages) == 50, f"expected cap=50, got {len(row.messages)}"
    # First stored message should be m10 (the 21st of 60 = m10)
    assert row.messages[0]["content"] == "m10"
    # Last stored message should be the last assistant turn
    assert row.messages[-1]["content"] == "r29"

    # 4. list_threads returns newest first.
    # First insert thread-2 so we can verify ordering.
    async with async_session() as db:
        await conversation_service.record_turn(
            db, user_id=user_id, thread_id="thread-2",
            messages=[{"role": "user", "content": "yo"}],
        )
        threads = await conversation_service.list_threads(db, user_id)
    print(f"4. list_threads → {len(threads)} threads, newest first: "
          f"{[t.thread_id for t in threads]}")
    assert len(threads) == 2
    assert threads[0].thread_id == "thread-2"  # most recent
    assert threads[1].thread_id == "thread-1"

    # 5. Channel filter.
    async with async_session() as db:
        await conversation_service.record_turn(
            db, user_id=user_id, thread_id="thread-3", channel="app",
            messages=[{"role": "user", "content": "in-app msg"}],
        )
        whatsapp = await conversation_service.list_threads(db, user_id, channel="whatsapp")
        app_threads = await conversation_service.list_threads(db, user_id, channel="app")
    print(f"5. channel filter → whatsapp={len(whatsapp)}, app={len(app_threads)}")
    assert len(whatsapp) == 2
    assert len(app_threads) == 1
    assert app_threads[0].thread_id == "thread-3"

    # 6. delete_thread removes the row.
    async with async_session() as db:
        ok = await conversation_service.delete_thread(
            db, user_id=user_id, thread_id="thread-1", channel="whatsapp",
        )
    print(f"6. delete thread-1 → {ok}")
    assert ok is True
    async with async_session() as db:
        threads = await conversation_service.list_threads(db, user_id)
    assert all(t.thread_id != "thread-1" for t in threads)

    # 7. Generate() wires the runtime write.
    # Stub the registry so we don't hit a real LLM.
    from app.providers import registry as provider_registry
    class StubProvider:
        api_key = "stub"; model = "stub"; base_url = None
        async def chat(self, messages, system=None, max_tokens=1024):
            return "stub-reply-for-test"
        def chat_stream(self, *a, **k): raise NotImplementedError
        async def validate(self): return True
        async def close(self): pass
    captured = {}
    async def fake_get(provider_id):
        captured["provider_id"] = provider_id
        return StubProvider()
    original_get = provider_registry.get_provider
    provider_registry.get_provider = fake_get  # type: ignore[assignment]

    from app.graph import generate

    state = {
        "message": "after-rewrite",
        "persona_id": ids["persona_id"],
    }
    config = {
        "configurable": {
            "user_id": user_id,
            "thread_id": "generated-thread",
            "channel": "app",
        }
    }
    update = await generate(state, config)
    print(f"\n7. generate() reply: {update['reply']!r}")
    # Conversation row should now exist for generated-thread with 2 messages.
    async with async_session() as db:
        row = await conversation_service.get_thread(
            db, user_id=user_id, thread_id="generated-thread", channel="app",
        )
    print(f"   → conversation row: {row.id if row else None}, messages={len(row.messages) if row else 0}")
    assert row is not None
    assert len(row.messages) == 2
    assert row.messages[0] == {"role": "user", "content": "after-rewrite"}
    assert row.messages[1] == {"role": "assistant", "content": "stub-reply-for-test"}
    assert row.persona_id == ids["persona_id"]

    # cleanup
    await _wipe(user_id)
    provider_registry.get_provider = original_get  # type: ignore[assignment]
    print("\nPhase 22 conversations OK")


asyncio.run(main())