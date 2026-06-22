"""Conversation sessions: registry in the store, messages from the checkpointer.
Per-user via the resolved user id."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .. import sessions as sessions_mod
from ..agent import get_run_agent, resolve_model
from ..auth import resolve_user_id, verify_gateway_key
from .deps import json_body, settings

router = APIRouter()


@router.get("/v1/sessions")
async def sessions_list(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    return {"sessions": await sessions_mod.list_sessions(uid)}


@router.post("/v1/sessions")
async def sessions_create(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await json_body(request)
    return JSONResponse(await sessions_mod.create_session(uid, body.get("title")))


@router.get("/v1/sessions/{thread_id}/messages")
async def sessions_messages(thread_id: str, request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    if not await sessions_mod.owns_session(uid, thread_id):
        return JSONResponse({"error": "not found"}, status_code=404)
    agent = await get_run_agent(
        settings, request.app.state.checkpointer, request.app.state.store, await resolve_model(settings, None, uid), uid
    )
    msgs = await sessions_mod.get_thread_messages(agent, uid, thread_id)
    return {"thread_id": thread_id, "messages": msgs}


@router.post("/v1/sessions/import")
async def sessions_import(request: Request):
    """Create a new conversation from an imported messages array."""
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await json_body(request)
    agent = await get_run_agent(
        settings, request.app.state.checkpointer, request.app.state.store, await resolve_model(settings, None, uid), uid
    )
    return JSONResponse(
        await sessions_mod.import_session(
            agent, uid, body.get("messages") or [], body.get("title")
        )
    )


@router.patch("/v1/sessions/{thread_id}")
async def sessions_rename(thread_id: str, request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await json_body(request)
    return JSONResponse(await sessions_mod.rename_session(uid, thread_id, body.get("title", "")))


@router.delete("/v1/sessions/{thread_id}")
async def sessions_delete(thread_id: str, request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    return JSONResponse(
        await sessions_mod.delete_session(request.app.state.checkpointer, uid, thread_id)
    )
