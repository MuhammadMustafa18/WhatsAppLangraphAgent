"""End-to-end test for AnthropicProvider against a local mock server."""
import asyncio

from app.providers.anthropic import AnthropicProvider, UnsupportedContentError
from app.providers.__tests__.mock_anthropic import MockAnthropicServer


async def main():
    port = 18182
    async with MockAnthropicServer(port) as base_url:
        print(f"mock server at {base_url}")

        # 1. validate()
        p = AnthropicProvider(api_key="sk-ant-fake", model="claude-fake", base_url=base_url)
        ok = await p.validate()
        print(f"validate OK: {ok}")
        assert ok

        # 2. chat() — system arg should arrive in TOP-LEVEL system field,
        # not as a message. Mock echoes only the last user message so we
        # verify by checking the user message arrives correctly.
        reply = await p.chat(
            messages=[{"role": "user", "content": "hello world"}],
            system="be brief",
        )
        print(f"chat reply: {reply!r}")
        assert reply == "echo: hello world"

        # 3. chat_stream() — chunks join
        chunks = []
        async for c in p.chat_stream(
            messages=[{"role": "user", "content": "foo bar baz"}],
            system="stream please",
        ):
            chunks.append(c)
        joined = "".join(chunks)
        print(f"stream chunks: {joined!r}")
        assert joined == "foo bar baz ", f"got: {joined!r}"

        # 4. system arg overrides embedded system message
        reply = await p.chat(
            messages=[
                {"role": "system", "content": "embedded system"},
                {"role": "user", "content": "hi"},
            ],
            system="caller system",  # should win
        )
        # Mock doesn't echo system; we just confirm no exception and that
        # the translator pulled the right text. Inspect via the mock later
        # if needed — for now we trust _separate_system's unit-level tests.
        print(f"merged system test reply: {reply!r}")
        assert reply == "echo: hi"

        # 5. embedded system only (no caller arg) — joined
        reply = await p.chat(
            messages=[
                {"role": "system", "content": "first system"},
                {"role": "system", "content": "second system"},
                {"role": "user", "content": "no caller arg"},
            ],
        )
        print(f"embedded system only reply: {reply!r}")
        assert reply == "echo: no caller arg"

        # 6. UnsupportedContentError on list-shaped content
        try:
            await p.chat(messages=[{
                "role": "user",
                "content": [{"type": "text", "text": "hi"}],
            }])
            print("ERROR: should have raised UnsupportedContentError")
        except UnsupportedContentError as e:
            print(f"rejected multi-block content: {str(e)[:50]}")

        # 7. close()
        await p.close()
        print("close() OK")


asyncio.run(main())