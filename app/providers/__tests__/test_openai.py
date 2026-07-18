"""End-to-end test for OpenAIProvider against a local mock server."""
import asyncio

from app.providers.openai import OpenAIProvider
from app.providers.__tests__.mock_openai import MockOpenAIServer


async def main():
    port = 18181
    async with MockOpenAIServer(port) as base_url:
        print(f"mock server at {base_url}")

        # 1. validate() with good key
        p = OpenAIProvider(api_key="sk-fake-good", model="fake-model", base_url=base_url)
        ok = await p.validate()
        print(f"validate OK: {ok}")
        assert ok

        # 2. chat() — full reply
        reply = await p.chat(
            messages=[{"role": "user", "content": "hello world"}],
            system="be brief",
        )
        print(f"chat reply: {reply!r}")
        assert reply == "echo: hello world"

        # 3. chat_stream() — chunks join to same answer
        chunks = []
        async for c in p.chat_stream(
            messages=[{"role": "user", "content": "foo bar baz"}],
            system="stream please",
        ):
            chunks.append(c)
        joined = "".join(chunks)
        print(f"stream chunks: {joined!r}")
        assert joined == "foo bar baz ", f"got: {joined!r}"

        # 4. validate() with bad key — server still returns 200 (it doesn't
        # actually check), so this doesn't catch bad keys. Real OpenAI would.
        # Skip this assertion; document that validate() catches transport
        # errors but not authorization errors in our mock.
        print("validate with bad key (mock returns 200):", await OpenAIProvider(
            api_key="sk-bad", model="fake-model", base_url=base_url
        ).validate())

        # 5. close()
        await p.close()
        print("close() OK")


asyncio.run(main())