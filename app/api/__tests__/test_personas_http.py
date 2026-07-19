"""End-to-end HTTP test for the /personas endpoints.

Boots a real FastAPI app via httpx.AsyncClient + ASGITransport — no
network needed. Registers a user, gets a JWT, then exercises the full
CRUD flow including model_override ownership checks.
"""
import asyncio
import httpx

from app.main import app
from app.db.models import User
from app.providers.registry import _cache
from sqlalchemy import select, delete
from app.db.engine import async_session
from app.db.models import Persona, Provider


async def _login(client: httpx.AsyncClient) -> str:
    """Register or log in mustafa, return access token."""
    r = await client.post("/auth/register", json={
        "username": "mustafa", "password": "password123"
    })
    if r.status_code in (400, 409):
        r = await client.post("/auth/login", json={
            "username": "mustafa", "password": "password123"
        })
    if r.status_code != 200:
        raise RuntimeError(f"auth failed: {r.status_code} {r.text}")
    return r.json()["access_token"]


async def _cleanup():
    """Wipe test rows so the test is repeatable."""
    async with async_session() as s:
        u = (await s.execute(select(User).where(User.username == "mustafa"))).scalar_one_or_none()
        if u:
            await s.execute(delete(Persona).where(Persona.user_id == u.id))
            await s.execute(delete(Provider).where(Provider.user_id == u.id))
            await s.commit()
    _cache.clear()


async def main():
    await _cleanup()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        token = await _login(client)
        headers = {"Authorization": f"Bearer {token}"}
        print(f"got token (len={len(token)})")

        # 1. Unauthenticated POST → 401 or 403
        r = await client.post("/personas", json={
            "name": "x", "system_prompt": "hi",
        })
        print(f"unauthenticated POST: {r.status_code} (expect 401 or 403)")
        assert r.status_code in (401, 403)

        # 2. Create a persona without model_override (default — chat layer
        #    will pick the user's default provider at runtime)
        r = await client.post("/personas", json={
            "name": "support",
            "system_prompt": "You are a helpful support agent.",
            "knowledge_base": "FAQ: returns within 30 days.",
            "is_active": True,
        }, headers=headers)
        print(f"create: {r.status_code}")
        assert r.status_code == 201, r.text
        created = r.json()
        print(f"  body: id={created['id']}, name={created['name']}, active={created['is_active']}")
        assert created["name"] == "support"
        assert created["system_prompt"] == "You are a helpful support agent."
        assert created["knowledge_base"] == "FAQ: returns within 30 days."
        assert created["model_override"] is None
        assert created["is_active"] is True
        support_id = created["id"]

        # 3. Duplicate name → 409 (clean pre-check, not a 500)
        r = await client.post("/personas", json={
            "name": "support",
            "system_prompt": "Another prompt.",
        }, headers=headers)
        print(f"duplicate name: {r.status_code} (expect 409)")
        assert r.status_code == 409

        # 4. List
        r = await client.get("/personas", headers=headers)
        assert r.status_code == 200
        listed = r.json()
        print(f"list: {len(listed)} personas")
        assert len(listed) == 1
        assert listed[0]["id"] == support_id

        # 5. Get one
        r = await client.get(f"/personas/{support_id}", headers=headers)
        assert r.status_code == 200
        assert r.json()["id"] == support_id

        # 6. Get unknown → 404
        r = await client.get("/personas/00000000-0000-0000-0000-000000000000", headers=headers)
        print(f"get unknown: {r.status_code} (expect 404)")
        assert r.status_code == 404

        # 7. PUT partial update
        r = await client.put(f"/personas/{support_id}", json={
            "system_prompt": "You are an updated support agent.",
        }, headers=headers)
        assert r.status_code == 200, r.text
        print(f"update prompt: {r.json()['system_prompt']}")
        assert r.json()["system_prompt"] == "You are an updated support agent."

        # 8. PUT with model_override pointing at a NON-EXISTENT provider
        #    → service silently drops it (clears the FK).
        r = await client.put(f"/personas/{support_id}", json={
            "model_override": "00000000-0000-0000-0000-000000000000",
        }, headers=headers)
        assert r.status_code == 200
        print(f"bad model_override cleared: {r.json()['model_override']}")
        assert r.json()["model_override"] is None

        # 9. Set up a real provider, then link persona to it.
        r = await client.post("/providers", json={
            "name": "test-prov",
            "type": "openai",
            "api_key": "sk-test-9999",
            "model": "gpt-4o",
        }, headers=headers)
        assert r.status_code == 201, r.text
        prov_id = r.json()["id"]

        r = await client.put(f"/personas/{support_id}", json={
            "model_override": prov_id,
        }, headers=headers)
        assert r.status_code == 200
        print(f"model_override set to real provider: {r.json()['model_override']}")
        assert r.json()["model_override"] == prov_id

        # 10. Validation: empty system_prompt rejected
        r = await client.post("/personas", json={
            "name": "bad",
            "system_prompt": "",
        }, headers=headers)
        print(f"empty prompt: {r.status_code} (expect 422)")
        assert r.status_code == 422

        # 11. DELETE
        r = await client.delete(f"/personas/{support_id}", headers=headers)
        assert r.status_code == 204
        print(f"deleted: {r.status_code}")

        # 12. Re-delete → 404
        r = await client.delete(f"/personas/{support_id}", headers=headers)
        print(f"re-delete: {r.status_code} (expect 404)")
        assert r.status_code == 404

    print("\nHTTP test OK")


asyncio.run(main())