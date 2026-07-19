"""Manual test for Phase 21b resolve helpers.

Run:
    .venv/Scripts/python.exe -m app.__tests__.test_resolve_helpers

Verifies the fallback chain for both helpers end-to-end against a
real SQLite DB. Wipes its own test rows before and after.
"""
import asyncio
import uuid

from sqlalchemy import select, delete

from app.db.engine import async_session
from app.db.models import Provider, User


async def _wipe_test_data(user_id: str) -> None:
    """Delete any prior test rows for the test user."""
    async with async_session() as db:
        await db.execute(
            delete(Provider).where(Provider.user_id == user_id)
        )
        # Personas table — uses CASCADE via FK
        from app.db.models import Persona
        await db.execute(
            delete(Persona).where(Persona.user_id == user_id)
        )
        await db.commit()


async def _setup_user_with_data(user_id: str) -> dict:
    """Seed a known state: 2 personas (one inactive), 2 providers (one default).

    Returns the IDs so the assertions can reference them.
    """
    from app.db.models import Persona
    async with async_session() as db:
        active_p = Persona(
            id=str(uuid.uuid4()), user_id=user_id, name="support",
            system_prompt="You are support.", is_active=True,
        )
        inactive_p = Persona(
            id=str(uuid.uuid4()), user_id=user_id, name="archived",
            system_prompt="You are archived.", is_active=False,
        )
        default_prov = Provider(
            id=str(uuid.uuid4()), user_id=user_id, name="default-prov",
            type="openai", api_key="enc-blob", model="gpt-4o",
            max_tokens=1024, is_default=True,
        )
        other_prov = Provider(
            id=str(uuid.uuid4()), user_id=user_id, name="other-prov",
            type="anthropic", api_key="enc-blob", model="claude-sonnet-4-5",
            max_tokens=1024, is_default=False,
        )
        db.add_all([active_p, inactive_p, default_prov, other_prov])
        await db.commit()
        await db.refresh(active_p)
        await db.refresh(inactive_p)
        return {
            "active_persona_id": active_p.id,
            "inactive_persona_id": inactive_p.id,
            "default_provider_id": default_prov.id,
            "other_provider_id": other_prov.id,
        }


async def _get_test_user_id() -> str:
    async with async_session() as db:
        u = (await db.execute(select(User).limit(1))).scalar_one_or_none()
        if u is None:
            raise SystemExit("no users in DB — register one first")
        return u.id


async def main():
    from app.graph import _resolve_persona, _resolve_provider

    user_id = await _get_test_user_id()
    await _wipe_test_data(user_id)
    ids = await _setup_user_with_data(user_id)

    # --- _resolve_persona ---
    print("\n=== _resolve_persona ===")

    # 1. explicit persona_id wins
    async with async_session() as db:
        p = await _resolve_persona(db, user_id, {"persona_id": ids["active_persona_id"]})
        print(f"1. explicit persona_id → name={p.name!r}")
        assert p.id == ids["active_persona_id"]

    # 2. explicit but wrong user → fallback (no error, just picks first active)
    async with async_session() as db:
        p = await _resolve_persona(db, user_id, {"persona_id": str(uuid.uuid4())})
        print(f"2. bad persona_id → falls back to active, name={p.name!r}")
        assert p.id == ids["active_persona_id"], "should fall back to active"

    # 3. no persona_id → first active (newest first)
    async with async_session() as db:
        p = await _resolve_persona(db, user_id, {})
        print(f"3. no persona_id → first active, name={p.name!r}")
        assert p.is_active is True
        assert p.id == ids["active_persona_id"]  # inserted second, but is_active wins

    # --- _resolve_provider ---
    print("\n=== _resolve_provider ===")
    active_persona = type("P", (), {"model_override": None, "id": "x"})()  # stub

    # 1. explicit provider_id wins
    async with async_session() as db:
        prov = await _resolve_provider(
            db, user_id,
            {"provider_id": ids["other_provider_id"]},
            active_persona,
        )
        print(f"1. explicit provider_id → name={prov.name!r}")
        assert prov.id == ids["other_provider_id"]

    # 2. no provider_id → user's default
    async with async_session() as db:
        prov = await _resolve_provider(db, user_id, {}, active_persona)
        print(f"2. no provider_id → default, name={prov.name!r}")
        assert prov.is_default is True
        assert prov.id == ids["default_provider_id"]

    # 3. persona.model_override takes precedence over default
    pinned = type("P", (), {"model_override": ids["other_provider_id"], "id": "x"})()
    async with async_session() as db:
        prov = await _resolve_provider(db, user_id, {}, pinned)
        print(f"3. persona.model_override → other, name={prov.name!r}")
        assert prov.id == ids["other_provider_id"]

    # --- cleanup ---
    await _wipe_test_data(user_id)
    print("\nPhase 21b helpers OK")


asyncio.run(main())