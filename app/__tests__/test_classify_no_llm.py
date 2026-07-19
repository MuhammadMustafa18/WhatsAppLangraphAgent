"""End-to-end test for Phase 21d: classify() no longer asks the LLM.

Run:
    PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m app.__tests__.test_classify_no_llm

Verifies:
  - state['persona_id'] already set → classify returns {} (passthrough)
  - no persona_id, with user_id in config → resolves first active
    persona from DB and returns {"persona_id": <uuid>}
  - no persona_id, no user_id → returns {} (legacy fallback path)
  - no persona_id, with user_id, but user has zero active personas
    → returns {} (generate() will raise LookupError, no silent default)
  - no LLM is called. We assert by patching anthropic_client.chat and
    llm.chat to raise if invoked.
"""
import asyncio
import uuid

from sqlalchemy import select, delete

from app.db.engine import async_session
from app.db.models import Persona, User


async def _wipe(user_id: str) -> None:
    async with async_session() as db:
        await db.execute(delete(Persona).where(Persona.user_id == user_id))
        await db.commit()


async def _seed(user_id: str) -> dict[str, str]:
    async with async_session() as db:
        a = Persona(
            id=str(uuid.uuid4()), user_id=user_id, name="support",
            system_prompt="support prompt", is_active=True,
        )
        b = Persona(
            id=str(uuid.uuid4()), user_id=user_id, name="archived",
            system_prompt="archived prompt", is_active=False,
        )
        db.add_all([a, b])
        await db.commit()
        await db.refresh(a)
        return {"active_id": a.id, "inactive_id": b.id}


async def main():
    async with async_session() as db:
        u = (await db.execute(
            select(User).where(User.username == "mustafa")
        )).scalar_one_or_none()
        if u is None:
            raise SystemExit("mustafa not registered")
        user_id = u.id

    # Patch the legacy LLM clients to raise — proves classify never calls them.
    from app import anthropic_client, llm
    anthropic_client.chat = lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("classify called anthropic_client.chat"))
    llm.chat = lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("classify called llm.chat"))

    from app.graph import classify

    # 1. persona_id already set → passthrough
    result = await classify({"message": "hi", "persona_id": "pre-set-uuid"})
    print("1. persona_id set →", result)
    assert result == {}, "passthrough returns empty dict"

    # 2. no persona_id, no user_id → empty dict (legacy path; no DB lookup)
    result = await classify({"message": "hi"})
    print("2. no user_id →", result)
    assert result == {}, "no user context returns empty"

    # 3. no persona_id, with user_id → resolves first active
    await _wipe(user_id)
    ids = await _seed(user_id)
    result = await classify(
        {"message": "help me"},
        config={"configurable": {"user_id": user_id}},
    )
    print("3. user_id set →", result)
    assert result == {"persona_id": ids["active_id"]}, \
        f"expected first active, got {result}"

    # 4. zero active personas → empty dict (generate() will raise LookupError)
    await _wipe(user_id)
    async with async_session() as db:
        only = Persona(
            id=str(uuid.uuid4()), user_id=user_id, name="disabled",
            system_prompt="x", is_active=False,
        )
        db.add(only)
        await db.commit()
    result = await classify(
        {"message": "hi"},
        config={"configurable": {"user_id": user_id}},
    )
    print("4. zero active →", result)
    assert result == {}, "no active persona returns empty (generate raises)"

    # cleanup
    await _wipe(user_id)
    print("\nPhase 21d classify() OK")


asyncio.run(main())