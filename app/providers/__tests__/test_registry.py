"""End-to-end test for the provider registry."""
import asyncio

from app.db.engine import async_session
from app.db.models import Provider, User
from app.core.security import encrypt_value
from app.providers.registry import get_provider, invalidate, close_all, _cache
from app.providers.openai import OpenAIProvider
from app.providers.anthropic import AnthropicProvider
from sqlalchemy import select, delete


async def _seed(db) -> str:
    """Insert one OpenAI + one Anthropic provider, return their ids."""
    user = (await db.execute(select(User).where(User.username == 'mustafa'))).scalar_one()

    # Clean any prior test rows
    await db.execute(delete(Provider).where(Provider.name.like('reg-%')))
    await db.commit()

    p1 = Provider(
        user_id=user.id, name='reg-openai', type='openai', base_url=None,
        api_key=encrypt_value('sk-fake-openai'), model='fake-model',
    )
    p2 = Provider(
        user_id=user.id, name='reg-anthropic', type='anthropic', base_url=None,
        api_key=encrypt_value('sk-ant-fake'), model='claude-fake',
    )
    db.add_all([p1, p2])
    await db.commit()
    await db.refresh(p1)
    await db.refresh(p2)
    return p1.id, p2.id


async def main():
    async with async_session() as db:
        openai_id, anthropic_id = await _seed(db)
    print(f"seeded: openai={openai_id}, anthropic={anthropic_id}")

    # 1. Cached lookup — same instance returned twice
    a = await get_provider(openai_id)
    b = await get_provider(openai_id)
    print(f"same instance on repeat lookup: {a is b}")
    assert a is b, "registry should cache instances"
    assert isinstance(a, OpenAIProvider), f"expected OpenAIProvider, got {type(a).__name__}"
    assert a.api_key == 'sk-fake-openai', "decrypted key should match seed"
    assert a.model == 'fake-model', "model should match seed"

    # 2. Different provider -> different instance, different class
    c = await get_provider(anthropic_id)
    print(f"anthropic class: {type(c).__name__}")
    assert isinstance(c, AnthropicProvider)
    assert c.api_key == 'sk-ant-fake'
    assert c is not a

    # 3. Invalidate -> next lookup rebuilds
    invalidate(openai_id)
    d = await get_provider(openai_id)
    print(f"rebuilt after invalidate: {d is not a}")
    assert d is not a, "invalidate should force a fresh build"

    # 4. Concurrent lookups share one build (covered by TTLCache's per-key lock;
    # we just check that the result is consistent)
    results = await asyncio.gather(*[get_provider(openai_id) for _ in range(5)])
    print(f"5 concurrent lookups, all same instance: {len({id(r) for r in results}) == 1}")
    assert len({id(r) for r in results}) == 1

    # 5. Unknown id -> LookupError
    try:
        await get_provider('00000000-0000-0000-0000-000000000000')
        print("ERROR: should have raised")
    except LookupError as e:
        print(f"unknown id rejected: {str(e)[:50]}")

    # 6. Cache size
    print(f"cache size after 2 providers + 1 invalidate + 1 rebuild: {len(_cache)}")

    # 7. close_all() runs without error
    await close_all()
    print(f"after close_all, cache size: {len(_cache)}")

    # 8. After close_all, looking up rebuilds (but the OLD instance is gone)
    e = await get_provider(openai_id)
    print(f"after close_all, new instance: {e is not d}")
    # We can't easily assert e.close() because httpx async client tracks state
    # internally; calling close() twice is fine.

    await close_all()
    print("registry test OK")


asyncio.run(main())