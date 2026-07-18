"""Tiny mock of Anthropic's /v1/messages + /v1/models endpoints.

Mirrors the SSE event shape Anthropic's API emits:
  event: message_start
  data: {"type":"message_start","message":{...}}

  event: content_block_start
  data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}

  event: content_block_delta
  data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hi"}}

  event: content_block_stop
  data: {"type":"content_block_stop","index":0}

  event: message_stop
  data: {"type":"message_stop"}

For non-streaming requests we just return the final assembled text.
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

    @app.get("/v1/models")
    async def models():
        return {
            "data": [{"id": "claude-fake", "type": "model"}],
            "has_more": False,
        }

    @app.post("/v1/messages")
    async def messages(request: Request):
        body = await request.json()
        stream = body.get("stream", False)
        # Echo the last user message so the test can assert on it.
        last_user = next(
            (m for m in reversed(body.get("messages", [])) if m["role"] == "user"),
            {"content": ""},
        )
        text = last_user["content"]

        if stream:
            async def gen():
                msg_id = "msg_" + uuid.uuid4().hex[:24]
                yield "event: message_start\n"
                yield "data: " + json.dumps({
                    "type": "message_start",
                    "message": {
                        "id": msg_id,
                        "type": "message",
                        "role": "assistant",
                        "model": body["model"],
                        "content": [],
                        "stop_reason": None,
                        "usage": {"input_tokens": 1, "output_tokens": 1},
                    },
                }) + "\n\n"

                yield "event: content_block_start\n"
                yield "data: " + json.dumps({
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {"type": "text", "text": ""},
                }) + "\n\n"

                for word in text.split():
                    yield "event: content_block_delta\n"
                    yield "data: " + json.dumps({
                        "type": "content_block_delta",
                        "index": 0,
                        "delta": {"type": "text_delta", "text": word + " "},
                    }) + "\n\n"

                yield "event: content_block_stop\n"
                yield "data: " + json.dumps({
                    "type": "content_block_stop",
                    "index": 0,
                }) + "\n\n"

                yield "event: message_delta\n"
                yield "data: " + json.dumps({
                    "type": "message_delta",
                    "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                    "usage": {"output_tokens": 1},
                }) + "\n\n"

                yield "event: message_stop\n"
                yield "data: " + json.dumps({"type": "message_stop"}) + "\n\n"

            return StreamingResponse(gen(), media_type="text/event-stream")

        return JSONResponse({
            "id": "msg_" + uuid.uuid4().hex[:24],
            "type": "message",
            "role": "assistant",
            "model": body["model"],
            "content": [{"type": "text", "text": f"echo: {text}"}],
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {"input_tokens": 1, "output_tokens": 1},
        })

    return app


class MockAnthropicServer:
    """Async context manager running a fake Anthropic server in the background."""

    def __init__(self, port: int = 18182) -> None:
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

        async with httpx.AsyncClient() as c:
            for _ in range(50):
                try:
                    r = await c.get(
                        f"http://127.0.0.1:{self.port}/v1/models", timeout=0.5
                    )
                    if r.status_code == 200:
                        return f"http://127.0.0.1:{self.port}"
                except Exception:
                    pass
                await asyncio.sleep(0.1)
        raise RuntimeError("mock anthropic server failed to start")

    async def __aexit__(self, *exc) -> None:
        if self._server:
            self._server.should_exit = True
        if self._runner:
            await self._runner