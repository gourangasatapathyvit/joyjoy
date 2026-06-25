"""Runs API: capability advertisement, run creation, SSE event stream, and HITL
approval responses (tool progress + interactive approvals)."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from app.agent import runs as runs_mod
from app.sandbox import sandbox as sandbox_mod
from app.stores import sessions as sessions_mod
from app.stores import usersettings
from app.agent.agent import get_run_agent, resolve_model
from app.core.auth import resolve_user_id, verify_gateway_key
from app.core.context import AgentContext
from .deps import run_input_text, settings, thread_id_from

logger = logging.getLogger("joyjoy")
router = APIRouter()


@router.get("/v1/capabilities")
async def capabilities():
    # Advertised so hermes-webui's gateway_supports_approval() enables the runs API.
    # ``sandbox`` lets the client map mount-prefixed media paths (e.g. /workspace/x)
    # to workspace-relative tree paths and gate inline media on tree readiness.
    return {
        "name": "joyjoy",
        "features": {"approval_events": True, "run_approval_response": True, "tool_progress": True},
        "sandbox": {
            "enabled": sandbox_mod.is_enabled(settings),
            "mount_path": settings.sandbox_mount_path,
        },
    }


@router.post("/v1/runs")
async def create_run(request: Request):
    verify_gateway_key(request, settings)
    user_id = resolve_user_id(request, settings)
    body = await request.json()
    model = await resolve_model(settings, body.get("model"), user_id)
    thread_id = thread_id_from(request, body)
    text = run_input_text(body)
    reasoning = body.get("reasoning_effort")
    if reasoning is None:
        reasoning = body.get("reasoning")
    # Effective auto-approve: the client's per-run flag if sent, else the account
    # default. Drives server-side gate resolution AND is persisted on the session.
    auto_approve = body.get("auto_approve")
    auto_approve = bool(auto_approve) if auto_approve is not None else await usersettings.auto_approve_default(user_id)
    # Edit/regenerate: number of trailing user turns this message replaces in the
    # thread history (0 = plain append). Clamped to a sane bound.
    try:
        replace_turns = max(0, min(int(body.get("replace_turns") or 0), 1000))
    except (TypeError, ValueError):
        replace_turns = 0
    ws_id = await sessions_mod.workspace_id_for(user_id, thread_id)
    ctx = AgentContext(user_id=user_id, thread_id=thread_id, workspace_id=ws_id)
    agent = await get_run_agent(settings, request.app.state.checkpointer, request.app.state.store, model, user_id, reasoning=reasoning)
    run_id = await runs_mod.start_run(agent, ctx, text, auto_approve=auto_approve, replace_turns=replace_turns)
    logger.info("run start id=%s user=%s thread=%s ws=%s model=%s reasoning=%s auto_approve=%s", run_id, user_id, thread_id, ws_id, model, reasoning, auto_approve)
    try:
        await sessions_mod.record_session(
            user_id, thread_id, first_text=text, model=model, reasoning=reasoning, workspace_id=ws_id, auto_approve=auto_approve
        )
    except Exception:  # noqa: BLE001
        logger.warning("record_session failed", exc_info=True)
    return JSONResponse({"run_id": run_id, "id": run_id, "status": "running", "model": model})


@router.get("/v1/runs/{run_id}/events")
async def run_events(run_id: str, request: Request):
    verify_gateway_key(request, settings)

    async def gen():
        async for ev in runs_mod.event_stream(run_id):
            yield {"data": json.dumps(ev)}
        yield {"data": "[DONE]"}

    return EventSourceResponse(gen())


@router.post("/v1/runs/{run_id}/approvals/{approval_id}/respond")
async def run_approval_respond(run_id: str, approval_id: str, request: Request):
    verify_gateway_key(request, settings)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    choice = body.get("choice") or body.get("decision") or "approve"
    ok = runs_mod.respond_approval(run_id, approval_id, choice)
    return JSONResponse({"ok": ok})


@router.post("/v1/runs/{run_id}/cancel")
async def run_cancel(run_id: str, request: Request):
    verify_gateway_key(request, settings)
    return JSONResponse({"ok": runs_mod.cancel_run(run_id)})
