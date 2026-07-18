"""Tiny mock of OpenAI's /chat/completions + /models endpoints.

Used by Phase 15 verification. NOT a test fixture — it's a live HTTP server
so we can prove OpenAIProvider actually speaks HTTP. Started and stopped
inside a single test script.
"""
import asyncio
import json
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
import uvicorn


def make_app() -> FastAPI:
    app = FastAPI()

    @app.get("/models")
    async def models():
        return {
            "object": "list",
            "data": [{"id": "fake-model", "object": "model"}],
        }

    @app.post("/chat/completions")
    async def chat_completions(request: Request):
        body = await request.json()
        stream = body.get("stream", False)
        last_user = next(
            (m for m in reversed(body.get("messages", [])) if m["role"] == "user"),
            {"content": ""},
        )
        text = last_user["content"]

        if stream:
            async def gen():
                # Emit role + content tokens in OpenAI's SSE shape.
                yield "data: " + json.dumps({
                    "id": "chatcmpl-fake",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": body["model"],
                    "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
                }) + "\n\n"
                for word in text.split():
                    yield "data: " + json.dumps({
                        "id": "chatcmpl-fake",
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": body["model"],
                        "choices": [{"index": 0, "delta": {"content": word + " "}, "finish_reason": None}],
                    }) + "\n\n"
                yield "data: " + json.dumps({
                    "id": "chatcmpl-fake",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": body["model"],
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                }) + "\n\n"
                yield "data: [DONE]\n\n"
            return StreamingResponse(gen(), media_type="text/event-stream")

        return JSONResponse({
            "id": "chatcmpl-" + uuid.uuid4().hex[:8],
            "object": "chat.completion",
            "created": int(time.time()),
            "model": body["model"],
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": f"echo: {text}"},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        })

    return app


class MockOpenAIServer:
    """Async context manager that runs a fake OpenAI server in the background.

    Usage:
        async with MockOpenAIServer(port=18181) as base_url:
            provider = OpenAIProvider(..., base_url=base_url)
            ...
    """

    def __init__(self, port: int = 18181) -> None:
        self.port = port
        self._server = None
        self._runner = None

    async def __aenter__(self) -> str:
        import httpx
        config = uvicorn.Config(
            make_app(), host="127.0.0.1", port=self.port, log_level="warning"
        )
        self._server = uvicorn.Server(config)
        self._runner = asyncio.create_task(self._server.serve())

        # Poll until the server is accepting connections.
        async with httpx.AsyncClient() as c:
            for _ in range(50):
                try:
                    r = await c.get(
                        f"http://127.0.0.1:{self.port}/models", timeout=0.5
                    )
                    if r.status_code == 200:
                        return f"http://127.0.0.1:{self.port}"
                except Exception:
                    pass
                await asyncio.sleep(0.1)
        raise RuntimeError("mock server failed to start")

    async def __aexit__(self, *exc) -> None:
        if self._server:
            self._server.should_exit = True
        if self._runner:
            await self._runner