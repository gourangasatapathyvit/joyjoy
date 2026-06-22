"""OpenAI-compatible chat completions (SSE when stream=true; model passthrough)."""

from __future__ import annotations

import json
import logging
import time
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from ..agent import chunk_text, get_agent, invoke_once, resolve_model, stream_messages
from ..auth import resolve_user_id, verify_gateway_key
from ..context import AgentContext
from .deps import last_user_text, settings, thread_id_from

logger = logging.getLogger("joyjoy")
router = APIRouter()


@router.post("/v1/chat/completions")
async def chat_completions(request: Request):
    verify_gateway_key(request, settings)
    user_id = resolve_user_id(request, settings)
    body = await request.json()
    do_stream = bool(body.get("stream", True))
    model = await resolve_model(settings, body.get("model"), user_id)  # passthrough (validated)
    thread_id = thread_id_from(request, body)
    text = last_user_text(body.get("messages") or [])
    reasoning = body.get("reasoning_effort")
    if reasoning is None:
        reasoning = body.get("reasoning")
    ctx = AgentContext(user_id=user_id, thread_id=thread_id)
    agent = await get_agent(settings, request.app.state.checkpointer, request.app.state.store, model, user_id, reasoning=reasoning)

    cid = f"chatcmpl-{uuid.uuid4().hex}"
    created = int(time.time())

    if not do_stream:
        answer = await invoke_once(agent, text, ctx)
        return JSONResponse(
            {
                "id": cid,
                "object": "chat.completion",
                "created": created,
                "model": model,
                "choices": [
                    {"index": 0, "message": {"role": "assistant", "content": answer}, "finish_reason": "stop"}
                ],
            }
        )

    async def event_gen():
        def frame(delta: dict, finish=None):
            return {
                "data": json.dumps(
                    {
                        "id": cid,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": model,
                        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
                    }
                )
            }

        yield frame({"role": "assistant"})
        try:
            async for chunk, _meta in stream_messages(agent, text, ctx):
                piece = chunk_text(chunk)
                if piece:
                    yield frame({"content": piece})
        except Exception as exc:  # noqa: BLE001 - surface into the SSE stream
            logger.exception("stream error user=%s thread=%s", user_id, thread_id)
            yield frame({"content": f"\n[backend error: {exc}]"}, finish="stop")
            yield {"data": "[DONE]"}
            return
        yield frame({}, finish="stop")
        yield {"data": "[DONE]"}

    return EventSourceResponse(event_gen())
