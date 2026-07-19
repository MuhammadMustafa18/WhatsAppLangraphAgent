"""End-to-end test for Phase 21c: generate() goes through the registry.

Run:
    PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m app.__tests__.test_generate_runtime

Verifies:
  - generate() resolves persona + provider from DB via the helpers
  - generate() calls provider_registry.get_provider(...).chat(...) with
    the right system prompt (from the persona) and message list
  - Returns {reply, messages} with both turns appended
  - Knowledge base gets merged into the system prompt
  - Legacy path (no user_id in config) still works for tests/scripts
"""
import asyncio
import uuid
from typing import Any

from sqlalchemy import select, delete

from app.db.engine import async_session
from app.db.models import Persona, Provider, User
from app.core.security import encrypt_value
from app.providers import registry as provider_registry


class StubProvider:
    """Records what was called, returns a canned reply.

    Used as a drop-in for `provider_registry.get_provider` so we don't
    hit a real LLM. Implements the BaseProvider ABC minimally.
    """
    api_key: str = "stub"
    model: str = "stub-model"
    base_url: str | None = None

    def __init__(self, *, provider_id: str, name: str) -> None:
        self.provider_id = provider_id
        self.name = name
        self.calls: list[dict[str, Any]] = []

    async def chat(self, messages, system=None, max_tokens=1024):
        self.calls.append({
            "messages": list(messages),
            "system": system,
            "max_tokens": max_tokens,
        })
        return f"stub-reply-for-{self.name}"

    def chat_stream(self, messages, system=None, max_tokens=1024):
        raise NotImplementedError

    async def validate(self) -> bool:
        return True

    async def close(self) -> None:
        pass


async def _wipe_test_data(user_id: str) -> None:
    async with async_session() as db:
        await db.execute(delete(Provider).where(Provider.user_id == user_id))
        await db.execute(delete(Persona).where(Persona.user_id == user_id))
        await db.commit()


async def _setup(user_id: str) -> dict[str, str]:
    async with async_session() as db:
        p = Persona(
            id=str(uuid.uuid4()), user_id=user_id, name="support",
            system_prompt="You are support. Be brief.",
            knowledge_base="FAQ: returns within 30 days.",
            is_active=True,
        )
        prov = Provider(
            id=str(uuid.uuid4()), user_id=user_id, name="gen-test-prov",
            type="openai", api_key=encrypt_value("sk-fake"),
            model="gpt-4o", max_tokens=512, is_default=True,
        )
        db.add_all([p, prov])
        await db.commit()
        await db.refresh(p)
        await db.refresh(prov)
        return {"persona_id": p.id, "provider_id": prov.id}


def _patch_registry(stub: StubProvider) -> None:
    """Bypass the real registry build and return our stub directly."""
    async def fake_get(provider_id: str):
        # Match the requested id to the stub so the test is realistic.
        stub.provider_id = provider_id
        return stub
    provider_registry.get_provider = fake_get  # type: ignore[assignment]


async def main():
    async with async_session() as db:
        u = (await db.execute(
            select(User).where(User.username == "mustafa")
        )).scalar_one_or_none()
        if u is None:
            raise SystemExit("mustafa not registered — run test_providers_http first")
        user_id = u.id

    await _wipe_test_data(user_id)
    ids = await _setup(user_id)

    stub = StubProvider(provider_id=ids["provider_id"], name="gen-test-prov")
    _patch_registry(stub)

    from app.graph import generate

    # 1. New runtime path: user_id in config, persona_id explicit
    state = {
        "message": "how do I return a product?",
        "persona_id": ids["persona_id"],
    }
    config = {"configurable": {"user_id": user_id, "thread_id": "test-thread-1"}}
    update = await generate(state, config)
    print("\n=== runtime path (explicit ids) ===")
    print(f"reply: {update['reply']!r}")
    print(f"history len: {len(update['messages'])}")
    assert update["reply"] == "stub-reply-for-gen-test-prov"
    assert len(update["messages"]) == 2
    assert update["messages"][0]["role"] == "user"
    assert update["messages"][1]["role"] == "assistant"
    # The stub should have been called once with our merged system prompt
    assert len(stub.calls) == 1
    sys_arg = stub.calls[0]["system"]
    print(f"system prompt length: {len(sys_arg)} chars")
    assert "You are support." in sys_arg, "system prompt from persona"
    assert "FAQ: returns within 30 days." in sys_arg, "knowledge_base merged"
    # Message list: 1 user message, no prior history
    assert len(stub.calls[0]["messages"]) == 1
    assert stub.calls[0]["messages"][0]["role"] == "user"
    assert stub.calls[0]["max_tokens"] == 512, "uses persona's max_tokens"

    # 2. Follow-up turn: state carries prior history, generate appends
    state2 = {
        "message": "and what about refunds?",
        "persona_id": ids["persona_id"],
        "messages": update["messages"],  # carry over
    }
    stub.calls.clear()
    update2 = await generate(state2, config)
    print("\n=== runtime path (turn 2) ===")
    print(f"history len: {len(update2['messages'])}")
    assert len(update2["messages"]) == 4, "prior 2 turns + new 2"
    assert len(stub.calls[0]["messages"]) == 3, "1 prior user + 1 prior assistant + 1 new user"

    # 3. No user_id in config → legacy path. Stub out the OpenAI client
    # so we don't try to hit FreeLLMAPI for real.
    from app import llm as llm_mod
    class FakeCompletions:
        def create(self, **kwargs):
            class FakeChoice:
                class FakeMessage:
                    content = "legacy-reply"
                message = FakeMessage()
            class FakeResp:
                choices = [FakeChoice()]
            return FakeResp()
    class FakeChat:
        completions = FakeCompletions()
    class FakeOpenAI:
        chat = FakeChat()
    llm_mod._get_client = lambda: FakeOpenAI()

    legacy_state = {"message": "hi", "persona": "personal"}
    update3 = await generate(legacy_state)
    print("\n=== legacy path (no config) ===")
    print(f"reply: {update3['reply']!r}")
    print(f"history len: {len(update3['messages'])}")
    assert update3["reply"] == "legacy-reply"
    assert len(update3["messages"]) == 2

    # cleanup
    await _wipe_test_data(user_id)
    provider_registry.invalidate(ids["provider_id"])
    print("\nPhase 21c generate() runtime OK")


asyncio.run(main())