"""Shared bits for the route modules: the settings singleton and the small
request-parsing helpers several routers need. Kept here so the routers don't
import from each other (and don't re-derive the same helpers)."""

from __future__ import annotations

import uuid

from fastapi import Request

from ..config import get_settings

# One Settings instance for all routers (get_settings is lru_cached anyway).
settings = get_settings()


async def json_body(request: Request) -> dict:
    """Parse a JSON request body to a dict (``{}`` on empty/invalid)."""
    try:
        body = await request.json()
        return body if isinstance(body, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def last_user_text(messages: list) -> str:
    """The latest user message's text from an OpenAI-style messages array."""
    for m in reversed(messages or []):
        if (m or {}).get("role") == "user":
            c = m.get("content")
            if isinstance(c, str):
                return c
            if isinstance(c, list):
                return "".join(
                    p.get("text", "") for p in c if isinstance(p, dict) and p.get("type") == "text"
                )
    return ""


def thread_id_from(request: Request, body: dict) -> str:
    """Resolve the conversation thread id from headers / body (new id if absent)."""
    return (
        request.headers.get(settings.thread_id_header.lower())
        or request.headers.get("x-hermes-session-id")  # hermes-webui sends this
        or body.get("thread_id")
        or f"t-{uuid.uuid4().hex}"
    )


def run_input_text(body: dict) -> str:
    """Extract the user's prompt text from a /v1/runs body (input str | [msgs] | message)."""
    inp = body.get("input")
    if isinstance(inp, str):
        return inp
    if isinstance(inp, list):
        return last_user_text(inp)
    if isinstance(body.get("messages"), list):
        return last_user_text(body["messages"])
    return str(body.get("message") or "")
