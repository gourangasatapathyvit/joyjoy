"""Conversation sessions: registry in the store, messages from the checkpointer.
Per-user via the resolved user id."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.sandbox import sandbox as sandbox_mgr
from app.stores import sessions as sessions_mod
from app.agent.agent import get_run_agent, resolve_model
from app.core.auth import resolve_user_id, verify_gateway_key
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
    owner = await sessions_mod.session_owner(thread_id)
    if owner is None:
        # Brand-new thread the client created optimistically; nothing persisted yet.
        return {"thread_id": thread_id, "messages": []}
    if owner != uid:
        return JSONResponse({"error": "not found"}, status_code=404)
    agent = await get_run_agent(
        settings, request.app.state.checkpointer, request.app.state.store, await resolve_model(settings, None, uid), uid
    )
    msgs = await sessions_mod.get_thread_messages(agent, uid, thread_id)
    # Per-thread UI telemetry (Context Display usage + Sources) persisted from the
    # last run, so they repopulate on reload.
    meta = await sessions_mod.get_thread_meta(thread_id)
    return {"thread_id": thread_id, "messages": msgs, "meta": meta}


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
async def sessions_update(thread_id: str, request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await json_body(request)
    return JSONResponse(
        await sessions_mod.update_session(
            uid,
            thread_id,
            title=body.get("title") if "title" in body else None,
            auto_approve=body.get("auto_approve") if "auto_approve" in body else None,
            pinned=body.get("pinned") if "pinned" in body else None,
        )
    )


@router.delete("/v1/sessions/{thread_id}")
async def sessions_delete(thread_id: str, request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    # Resolve BEFORE delete_session removes the Session row — workspace_id_for
    # needs that row to return the thread's real (fork-aware) workspace segment;
    # once the row is gone it can only fall back to a synthetic "default-{uid}"
    # value that doesn't correspond to any real folder.
    ws = await sessions_mod.workspace_id_for(uid, thread_id) if sandbox_mgr.is_enabled(settings) else None
    res = await sessions_mod.delete_session(request.app.state.checkpointer, uid, thread_id)
    # Delete just this thread's subfolder inside the user's SHARED sandbox
    # container — not kill_session (full container teardown), which is now
    # user-scoped and would take every other thread's sandbox down with it.
    # Note: a forked session shares its parent's workspace segment, so deleting
    # either one currently reclaims the files both point at (same tradeoff the
    # old per-thread-container kill_session call already made).
    if sandbox_mgr.is_enabled(settings) and ws:
        try:
            await sandbox_mgr.delete_thread_workspace(settings, uid, ws)
        except Exception:  # noqa: BLE001 - cleanup is best-effort
            pass
    return JSONResponse(res)
