"""End-to-end HTTP test for the /providers endpoints.

Boots a real FastAPI app via httpx.AsyncClient + ASGITransport — no
network needed. Registers a user, gets a JWT, then exercises the full
CRUD + validate + default flow.
"""
import asyncio
import httpx

from app.main import app
from app.db.models import User
from app.repositories import provider_repo
from app.providers.registry import close_all, _cache
from sqlalchemy import select, delete
from app.db.engine import async_session
from app.db.models import Provider


async def _login(client: httpx.AsyncClient) -> str:
    """Register or log in mustafa, return access token."""
    r = await client.post("/auth/register", json={
        "username": "mustafa", "password": "password123"
    })
    if r.status_code == 400 or r.status_code == 409:
        r = await client.post("/auth/login", json={
            "username": "mustafa", "password": "password123"
        })
    if r.status_code != 200:
        raise RuntimeError(f"auth failed: {r.status_code} {r.text}")
    return r.json()["access_token"]


async def _cleanup():
    """Wipe test rows so the test is repeatable."""
    async with async_session() as s:
        # Find mustafa's user id, delete their providers
        u = (await s.execute(select(User).where(User.username == "mustafa"))).scalar_one_or_none()
        if u:
            await s.execute(delete(Provider).where(Provider.user_id == u.id))
            await s.commit()
    _cache.clear()


async def main():
    await _cleanup()
    await close_all()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        # 1. Auth
        token = await _login(client)
        headers = {"Authorization": f"Bearer {token}"}
        print(f"got token (len={len(token)})")

        # 2. Unauthenticated POST → 401 or 403 (HTTPBearer's default is 403)
        r = await client.post("/providers", json={
            "name": "x", "type": "openai", "api_key": "sk", "model": "m"
        })
        print(f"unauthenticated POST: {r.status_code} (expect 401 or 403)")
        assert r.status_code in (401, 403)

        # 3. Create
        r = await client.post("/providers", json={
            "name": "first",
            "type": "openai",
            "api_key": "sk-first-plain-1234",
            "model": "gpt-4o",
            "max_tokens": 1024,
        }, headers=headers)
        print(f"create: {r.status_code}")
        assert r.status_code == 201, r.text
        created = r.json()
        print(f"  body: id={created['id']}, name={created['name']}, masked={created['api_key_masked']}")
        assert created["api_key_plain"] == "sk-first-plain-1234", "plaintext returned once"
        assert created["api_key_masked"] == "...1234", "masked as last4"
        assert created["is_default"] is True, "first provider auto-defaults"
        first_id = created["id"]

        # 4. List
        r = await client.get("/providers", headers=headers)
        assert r.status_code == 200
        listed = r.json()
        print(f"list: {len(listed)} providers")
        assert len(listed) == 1
        # No plaintext in list response
        assert "api_key_plain" not in listed[0]
        assert listed[0]["api_key_masked"] == "...1234"

        # 5. Get one
        r = await client.get(f"/providers/{first_id}", headers=headers)
        assert r.status_code == 200
        assert r.json()["id"] == first_id

        # 6. Get unknown → 404
        r = await client.get("/providers/00000000-0000-0000-0000-000000000000", headers=headers)
        print(f"get unknown: {r.status_code} (expect 404)")
        assert r.status_code == 404

        # 7. PUT partial update
        r = await client.put(f"/providers/{first_id}", json={
            "model": "gpt-4-turbo",
        }, headers=headers)
        assert r.status_code == 200, r.text
        print(f"update model: {r.json()['model']}")
        assert r.json()["model"] == "gpt-4-turbo"

        # 8. PUT with new key — plaintext shown? No, only on POST.
        r = await client.put(f"/providers/{first_id}", json={
            "api_key": "sk-rotated-9999",
        }, headers=headers)
        assert r.status_code == 200
        updated = r.json()
        assert "api_key_plain" not in updated
        assert updated["api_key_masked"] == "...9999", "mask should reflect new key"
        print(f"update key: masked={updated['api_key_masked']}")

        # 9. Validate (mock provider returns True)
        # Use the openai mock at port 18181 if running, else expect
        # a network error (which the service treats as False).
        r = await client.post(f"/providers/{first_id}/validate", headers=headers)
        # Real OpenAI call would fail because we don't have a valid key.
        # Expect either 200 with valid=False, or 200 with valid=False
        # because the network call fails. The mock isn't running here.
        print(f"validate response: {r.status_code} {r.json()}")
        assert r.status_code == 200
        assert "valid" in r.json()

        # 10. Create a second provider, set as default
        r = await client.post("/providers", json={
            "name": "second",
            "type": "anthropic",
            "api_key": "sk-ant-test-5678",
            "model": "claude-sonnet-4-5",
        }, headers=headers)
        assert r.status_code == 201
        second = r.json()
        assert second["is_default"] is False, "second provider NOT default"
        second_id = second["id"]

        r = await client.post(f"/providers/{second_id}/default", headers=headers)
        assert r.status_code == 200
        print(f"promoted second to default: {r.json()['is_default']}")
        assert r.json()["is_default"] is True

        # Confirm first is no longer default
        r = await client.get(f"/providers/{first_id}", headers=headers)
        assert r.json()["is_default"] is False
        print(f"first is_default after switch: {r.json()['is_default']}")

        # 11. Custom type — needs base_url
        r = await client.post("/providers", json={
            "name": "ollama",
            "type": "custom",
            "api_key": "ollama",
            "model": "llama3",
        }, headers=headers)
        print(f"custom w/o base_url: {r.status_code} (expect 422)")
        assert r.status_code == 422, r.text

        r = await client.post("/providers", json={
            "name": "ollama",
            "type": "custom",
            "api_key": "ollama",
            "model": "llama3",
            "base_url": "http://localhost:11434/v1",
        }, headers=headers)
        assert r.status_code == 201
        ollama = r.json()
        print(f"custom with base_url: created, type={ollama['type']}")
        assert ollama["type"] == "custom"

        # 12. DELETE
        r = await client.delete(f"/providers/{ollama['id']}", headers=headers)
        assert r.status_code == 204
        print(f"deleted ollama provider: {r.status_code}")

        r = await client.delete(f"/providers/{ollama['id']}", headers=headers)
        assert r.status_code == 404
        print(f"re-delete: {r.status_code} (expect 404)")

        # 13. Bad type
        r = await client.post("/providers", json={
            "name": "bad", "type": "nonsense",
            "api_key": "sk", "model": "m"
        }, headers=headers)
        print(f"bad type: {r.status_code} (expect 422)")
        assert r.status_code == 422

    print("\nHTTP test OK")


asyncio.run(main())