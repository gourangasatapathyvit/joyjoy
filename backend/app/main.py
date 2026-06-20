"""FastAPI app implementing hermes-webui's gateway contract.

Endpoints:
  GET  /healthz /health /health/detailed /v1/health   (gateway heartbeat)
  GET  /v1/models                                      (configured model registry)
  POST /v1/chat/completions   (OpenAI-compatible; SSE when stream=true; model passthrough)
Phase 2:
  POST /v1/runs + GET /v1/runs/{id}/events  (tool progress + HITL approvals)

Single process, many users: one compiled agent per model id (cached); each
request carries its own user_id + thread_id for isolation.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from . import runs as runs_mod
from .agent import (
    PROVIDER_TYPES,
    chunk_text,
    delete_user_mcp,
    delete_user_model,
    delete_user_skill,
    describe_mcp,
    describe_models,
    get_agent,
    get_run_agent,
    invoke_once,
    list_skills,
    merged_model_specs,
    read_memory,
    read_skill_content,
    resolve_model,
    save_user_mcp,
    save_user_model,
    save_user_skill,
    stream_messages,
    toggle_user_mcp,
    toggle_user_skill,
    write_memory,
)
from .auth import resolve_user_id, verify_gateway_key
from .config import get_settings
from .context import AgentContext
from .persistence import open_persistence

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("joyjoy")
settings = get_settings()


def _load_env_file_into_environ() -> None:
    """Load ``.env`` KEY=VALUE pairs into os.environ (without overriding existing vars).

    Lets MCP server configs reference secrets via ``${VAR}`` (e.g. an API key) so the
    key stays out of the committed MCP config. pydantic loads .env into Settings but
    not into os.environ — this fills that gap for MCP subprocess ``env`` expansion.
    """
    import os

    for envfile in (".env", "../.env"):
        try:
            if not os.path.isfile(envfile):
                continue
            with open(envfile, encoding="utf-8") as f:
                for raw in f:
                    line = raw.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, val = line.partition("=")
                    key, val = key.strip(), val.strip()
                    if val[:1] not in ('"', "'", "{", "["):  # strip inline comment on simple values
                        val = val.split("  #", 1)[0].split(" #", 1)[0].strip()
                    if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
                        val = val[1:-1]
                    if key and key not in os.environ:
                        os.environ[key] = val
        except Exception:
            logger.debug("env load from %s failed", envfile, exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _load_env_file_into_environ()
    async with open_persistence(settings) as (checkpointer, store):
        app.state.checkpointer = checkpointer
        app.state.store = store
        await get_agent(settings, checkpointer, store, settings.default_model, "default")  # warm default
        logger.info(
            "joyjoy backend ready (env=%s, prod=%s, models=%s)",
            settings.app_env, settings.is_prod, list(settings.model_specs),
        )
        yield


app = FastAPI(title="joyjoy backend", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# joyjoy branding: serve the favicon + brand assets for anyone hitting the API in a browser
# (e.g. /docs). Files live in backend/static (copied from the joyjoy brand kit).
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")


@app.get("/favicon.ico", include_in_schema=False)
async def _favicon_ico():
    return FileResponse(os.path.join(_STATIC_DIR, "favicon.ico"), media_type="image/x-icon")


@app.get("/favicon.svg", include_in_schema=False)
async def _favicon_svg():
    return FileResponse(os.path.join(_STATIC_DIR, "favicon.svg"), media_type="image/svg+xml")


if os.path.isdir(_STATIC_DIR):
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


def _health_payload() -> dict:
    return {
        "status": "ok",
        "state": "alive",
        "gateway_state": "alive",
        "env": settings.app_env,
        "prod": settings.is_prod,
        "models": list(settings.model_specs),
    }


@app.get("/healthz")
async def healthz():
    return _health_payload()


@app.get("/health")
async def health():
    return _health_payload()


@app.get("/health/detailed")
async def health_detailed():
    return _health_payload()


@app.get("/v1/health")
async def v1_health():
    return _health_payload()


@app.get("/v1/models")
async def list_models(request: Request):
    """Global catalog + the calling user's own models, so the picker is per-user.
    Each item carries its ``provider`` so the UI can group/label the picker."""
    uid = resolve_user_id(request, settings)
    specs = merged_model_specs(settings, uid)
    return {
        "object": "list",
        "data": [
            {"id": mid, "object": "model", "owned_by": "joyjoy", "provider": s.get("provider", "azure_openai")}
            for mid, s in specs.items()
        ],
    }


@app.get("/v1/mcp/servers")
async def mcp_servers(request: Request):
    """Global + per-user MCP servers for the calling user (read-only; UI MCP tab)."""
    verify_gateway_key(request, settings)
    user_id = resolve_user_id(request, settings)
    servers, _tools = await describe_mcp(settings, user_id)
    return {"servers": servers, "toggle_supported": False}


@app.get("/v1/mcp/tools")
async def mcp_tools(request: Request):
    """Tools exposed by the user's global + per-user MCP servers (UI MCP tab)."""
    verify_gateway_key(request, settings)
    user_id = resolve_user_id(request, settings)
    _servers, tools = await describe_mcp(settings, user_id)
    return {"tools": tools, "total": len(tools)}


@app.get("/v1/skills")
async def skills(request: Request):
    """Global skills (read-only) + per-user skills for the calling user (UI Skills tab)."""
    verify_gateway_key(request, settings)
    user_id = resolve_user_id(request, settings)
    items = await list_skills(settings, request.app.state.store, user_id)
    return {"skills": items}


@app.get("/v1/skills/content")
async def skill_content(request: Request):
    """Read-only content of one skill (SKILL.md or a linked file) for the UI viewer."""
    verify_gateway_key(request, settings)
    user_id = resolve_user_id(request, settings)
    name = request.query_params.get("name") or ""
    file = request.query_params.get("file") or None
    data = await read_skill_content(settings, request.app.state.store, user_id, name, file)
    return JSONResponse(data)


async def _json(request: Request) -> dict:
    try:
        body = await request.json()
        return body if isinstance(body, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


# ── Skills CRUD (user skills are writable; global skills are read-only) ──
@app.post("/v1/skills/save")
async def skills_save(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await _json(request)
    return JSONResponse(await save_user_skill(request.app.state.store, uid, body.get("name"), body.get("content")))


@app.post("/v1/skills/delete")
async def skills_delete(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await _json(request)
    return JSONResponse(await delete_user_skill(request.app.state.store, uid, body.get("name")))


@app.post("/v1/skills/toggle")
async def skills_toggle(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await _json(request)
    return JSONResponse(await toggle_user_skill(request.app.state.store, uid, body.get("name"), bool(body.get("enabled"))))


# ── MCP CRUD (user servers writable; global servers read-only) ──
@app.put("/v1/mcp/servers/{name}")
async def mcp_server_save(name: str, request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await _json(request)
    cfg = {k: body.get(k) for k in ("command", "args", "url", "headers", "env", "transport", "timeout", "enabled") if body.get(k) not in (None, "")}
    return JSONResponse(save_user_mcp(settings, uid, name, cfg))


@app.delete("/v1/mcp/servers/{name}")
async def mcp_server_delete(name: str, request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    return JSONResponse(delete_user_mcp(settings, uid, name))


@app.patch("/v1/mcp/servers/{name}")
async def mcp_server_toggle(name: str, request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await _json(request)
    return JSONResponse(toggle_user_mcp(settings, uid, name, bool(body.get("enabled"))))


# ── Models / Providers CRUD (user models writable; global models read-only) ──
@app.get("/v1/models/config")
async def models_config(request: Request):
    """Global (read-only) + per-user models for the Providers tab, plus the
    provider field-schema the UI renders its add/edit forms from. Keys are masked."""
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    return {"models": describe_models(settings, uid), "providers": PROVIDER_TYPES}


@app.post("/v1/models/config/save")
async def models_config_save(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await _json(request)
    return JSONResponse(save_user_model(settings, uid, body))


@app.post("/v1/models/config/delete")
async def models_config_delete(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await _json(request)
    return JSONResponse(delete_user_model(settings, uid, body.get("id")))


# ── Memory (per-user notes / profile / soul) ──
@app.get("/v1/memory")
async def memory_get(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    mem = await read_memory(request.app.state.store, uid)
    return {**mem, "external_notes_enabled": False}


@app.post("/v1/memory/write")
async def memory_write(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await _json(request)
    return JSONResponse(await write_memory(request.app.state.store, uid, body.get("section"), body.get("content")))


def _last_user_text(messages: list) -> str:
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


def _thread_id(request: Request, body: dict) -> str:
    return (
        request.headers.get(settings.thread_id_header.lower())
        or request.headers.get("x-hermes-session-id")  # hermes-webui sends this
        or body.get("thread_id")
        or f"t-{uuid.uuid4().hex}"
    )


def _run_input_text(body: dict) -> str:
    """Extract the user's prompt text from a /v1/runs body (input str | [msgs] | message)."""
    inp = body.get("input")
    if isinstance(inp, str):
        return inp
    if isinstance(inp, list):
        return _last_user_text(inp)
    if isinstance(body.get("messages"), list):
        return _last_user_text(body["messages"])
    return str(body.get("message") or "")


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    verify_gateway_key(request, settings)
    user_id = resolve_user_id(request, settings)
    body = await request.json()
    do_stream = bool(body.get("stream", True))
    model = resolve_model(settings, body.get("model"), user_id)  # passthrough (validated)
    thread_id = _thread_id(request, body)
    text = _last_user_text(body.get("messages") or [])
    ctx = AgentContext(user_id=user_id, thread_id=thread_id)
    agent = await get_agent(settings, request.app.state.checkpointer, request.app.state.store, model, user_id)

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


@app.get("/v1/capabilities")
async def capabilities():
    # Advertised so hermes-webui's gateway_supports_approval() enables the runs API.
    return {
        "name": "joyjoy",
        "features": {"approval_events": True, "run_approval_response": True, "tool_progress": True},
    }


@app.post("/v1/runs")
async def create_run(request: Request):
    verify_gateway_key(request, settings)
    user_id = resolve_user_id(request, settings)
    body = await request.json()
    model = resolve_model(settings, body.get("model"), user_id)
    thread_id = _thread_id(request, body)
    text = _run_input_text(body)
    ctx = AgentContext(user_id=user_id, thread_id=thread_id)
    agent = await get_run_agent(settings, request.app.state.checkpointer, request.app.state.store, model, user_id)
    run_id = await runs_mod.start_run(agent, ctx, text)
    logger.info("run start id=%s user=%s thread=%s model=%s", run_id, user_id, thread_id, model)
    return JSONResponse({"run_id": run_id, "id": run_id, "status": "running", "model": model})


@app.get("/v1/runs/{run_id}/events")
async def run_events(run_id: str, request: Request):
    verify_gateway_key(request, settings)

    async def gen():
        async for ev in runs_mod.event_stream(run_id):
            yield {"data": json.dumps(ev)}
        yield {"data": "[DONE]"}

    return EventSourceResponse(gen())


@app.post("/v1/runs/{run_id}/approvals/{approval_id}/respond")
async def run_approval_respond(run_id: str, approval_id: str, request: Request):
    verify_gateway_key(request, settings)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    choice = body.get("choice") or body.get("decision") or "approve"
    ok = runs_mod.respond_approval(run_id, approval_id, choice)
    return JSONResponse({"ok": ok})


@app.post("/v1/runs/{run_id}/cancel")
async def run_cancel(run_id: str, request: Request):
    verify_gateway_key(request, settings)
    return JSONResponse({"ok": runs_mod.cancel_run(run_id)})
