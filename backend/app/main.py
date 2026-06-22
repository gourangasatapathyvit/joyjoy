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

from . import media as media_mod
from . import runs as runs_mod
from . import sessions as sessions_mod
from . import users as users_mod
from . import usersettings as usersettings_mod
from . import workspace as workspace_mod
from .agent import (
    PROVIDER_TYPES,
    chunk_text,
    delete_user_mcp,
    delete_user_model,
    delete_user_skill,
    delete_user_skill_file,
    describe_mcp,
    describe_models,
    get_agent,
    get_run_agent,
    import_user_skill,
    invoke_once,
    list_skills,
    merged_model_specs,
    model_supports_reasoning,
    read_memory,
    read_skill_content,
    resolve_model,
    save_user_mcp,
    save_user_model,
    save_user_skill,
    save_user_skill_file,
    stream_messages,
    test_model,
    toggle_user_mcp,
    toggle_user_skill,
    write_memory,
)
from .auth import (
    current_user_id,
    make_session_token,
    resolve_user_id,
    verify_gateway_key,
)
from .config import get_settings
from .context import AgentContext
from .db import ensure_encryption_key, init_db, seed_all
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
    # App relational DB: resolve the encryption key (generate+persist on first
    # run), create tables, seed the global catalogs. Dev → SQLite, prod → Postgres.
    ensure_encryption_key(settings)
    await init_db()
    await seed_all(settings)
    await users_mod.ensure_dev_user(settings)  # dev no-auth tenancy bucket
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


# ── Auth: username/password accounts, signed session cookie, email-OTP reset ──
def _set_session(resp: JSONResponse, user_id: str) -> JSONResponse:
    resp.set_cookie(
        settings.session_cookie,
        make_session_token(settings, user_id),
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        samesite="lax",
        secure=settings.is_prod,  # require HTTPS only in prod
        path="/",
    )
    return resp


@app.post("/v1/auth/signup")
async def auth_signup(request: Request):
    body = await _json(request)
    res = await users_mod.create_user(body.get("username"), body.get("email"), body.get("password"))
    if not res.get("ok"):
        return JSONResponse(res, status_code=409 if res.get("field") in ("username", "email") else 400)
    user = res["user"]
    return _set_session(JSONResponse({"ok": True, "user": user}), user["id"])


@app.post("/v1/auth/login")
async def auth_login(request: Request):
    body = await _json(request)
    user = await users_mod.verify_credentials(body.get("username"), body.get("password"))
    if not user:
        return JSONResponse({"ok": False, "error": "Invalid username or password."}, status_code=401)
    return _set_session(JSONResponse({"ok": True, "user": user}), user["id"])


@app.post("/v1/auth/logout")
async def auth_logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(settings.session_cookie, path="/")
    return resp


@app.get("/v1/auth/me")
async def auth_me(request: Request):
    uid = current_user_id(request, settings)
    if not uid:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)
    rec = await users_mod.get_user_by_id(uid)
    if not rec:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)
    return {"username": rec["username"], "email": rec.get("email")}


@app.get("/v1/auth/available")
async def auth_available(request: Request):
    """Live signup validation: is this username / email already taken?"""
    q = request.query_params
    out: dict = {}
    if q.get("username"):
        out["username_taken"] = await users_mod.username_taken(q["username"])
    if q.get("email"):
        out["email_taken"] = await users_mod.email_taken(q["email"])
    return out


@app.post("/v1/auth/forgot")
async def auth_forgot(request: Request):
    """Email a reset OTP. Always returns ok (never reveals whether the email exists)."""
    body = await _json(request)
    email = body.get("email") or ""
    out: dict = {"ok": True}
    res = await users_mod.create_reset_otp(settings, email)
    if res:
        otp, _user_id = res
        emailed = await users_mod.send_otp_email(settings, email, otp)
        if not emailed and not settings.is_prod:
            out["dev_otp"] = otp  # dev convenience when SMTP isn't configured
    return JSONResponse(out)


@app.post("/v1/auth/reset")
async def auth_reset(request: Request):
    body = await _json(request)
    if not users_mod.valid_password(body.get("password") or ""):
        return JSONResponse({"ok": False, "error": "Password must be at least 8 characters."}, status_code=400)
    res = await users_mod.verify_and_consume_otp(body.get("email"), body.get("otp"))
    if not res.get("ok"):
        return JSONResponse(res, status_code=400)
    await users_mod.set_password(res["user_id"], body.get("password"))
    return _set_session(JSONResponse({"ok": True}), res["user_id"])  # auto-login after reset


@app.post("/v1/auth/change-password")
async def auth_change_password(request: Request):
    uid = current_user_id(request, settings)
    if not uid:
        return JSONResponse({"ok": False, "error": "Not signed in."}, status_code=401)
    body = await _json(request)
    res = await users_mod.change_password(uid, body.get("current") or "", body.get("new") or "")
    return JSONResponse(res, status_code=200 if res.get("ok") else 400)


@app.get("/v1/models")
async def list_models(request: Request):
    """Global catalog + the calling user's own models, so the picker is per-user.
    Each item carries its ``provider`` so the UI can group/label the picker."""
    uid = resolve_user_id(request, settings)
    specs = await merged_model_specs(settings, uid)
    return {
        "object": "list",
        "data": [
            {
                "id": mid, "object": "model", "owned_by": "joyjoy",
                "provider": s.get("provider", "azure_openai"),
                "supports_reasoning": model_supports_reasoning(s),
            }
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
    items = await list_skills(settings, user_id)
    return {"skills": items}


@app.get("/v1/skills/content")
async def skill_content(request: Request):
    """Read-only content of one skill (SKILL.md or a linked file) for the UI viewer."""
    verify_gateway_key(request, settings)
    user_id = resolve_user_id(request, settings)
    name = request.query_params.get("name") or ""
    file = request.query_params.get("file") or None
    data = await read_skill_content(settings, user_id, name, file)
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
    return JSONResponse(await save_user_skill(uid, body.get("name"), body.get("content")))


@app.post("/v1/skills/delete")
async def skills_delete(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await _json(request)
    return JSONResponse(await delete_user_skill(uid, body.get("name")))


@app.post("/v1/skills/toggle")
async def skills_toggle(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await _json(request)
    return JSONResponse(await toggle_user_skill(uid, body.get("name"), bool(body.get("enabled"))))


# ── Multi-file user skills: per-file CRUD + zip import (global stays read-only) ──
@app.post("/v1/skills/files/save")
async def skills_file_save(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await _json(request)
    return JSONResponse(
        await save_user_skill_file(
            uid, body.get("skill"), body.get("path"), body.get("content") or "", body.get("encoding") or "utf-8"
        )
    )


@app.post("/v1/skills/files/delete")
async def skills_file_delete(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await _json(request)
    return JSONResponse(await delete_user_skill_file(uid, body.get("skill"), body.get("path")))


@app.post("/v1/skills/import")
async def skills_import(request: Request):
    """Create/replace a user skill from a base64-encoded zip ({name, zip_b64})."""
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await _json(request)
    return JSONResponse(await import_user_skill(uid, body.get("name"), body.get("zip_b64")))


# ── MCP CRUD (user servers writable; global servers read-only) ──
@app.put("/v1/mcp/servers/{name}")
async def mcp_server_save(name: str, request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await _json(request)
    cfg = {k: body.get(k) for k in ("command", "args", "url", "headers", "env", "transport", "timeout", "enabled") if body.get(k) not in (None, "")}
    return JSONResponse(await save_user_mcp(settings, uid, name, cfg))


@app.delete("/v1/mcp/servers/{name}")
async def mcp_server_delete(name: str, request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    return JSONResponse(await delete_user_mcp(settings, uid, name))


@app.patch("/v1/mcp/servers/{name}")
async def mcp_server_toggle(name: str, request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await _json(request)
    return JSONResponse(await toggle_user_mcp(settings, uid, name, bool(body.get("enabled"))))


# ── Models / Providers CRUD (user models writable; global models read-only) ──
@app.get("/v1/models/config")
async def models_config(request: Request):
    """Global (read-only) + per-user models for the Providers tab, plus the
    provider field-schema the UI renders its add/edit forms from. Keys are masked."""
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    return {"models": await describe_models(settings, uid), "providers": PROVIDER_TYPES}


@app.post("/v1/models/config/save")
async def models_config_save(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await _json(request)
    return JSONResponse(await save_user_model(settings, uid, body))


@app.post("/v1/models/config/delete")
async def models_config_delete(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await _json(request)
    return JSONResponse(await delete_user_model(settings, uid, body.get("id")))


@app.post("/v1/models/config/test")
async def models_config_test(request: Request):
    """Live probe for the Providers-tab status lights: does this model answer a
    standard call, and does it produce (visible) reasoning? Two small real requests."""
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await _json(request)
    model_id = body.get("id") or body.get("model")
    return JSONResponse(await test_model(settings, uid, model_id))


# ── Memory (per-user AGENTS.md — deepagents MemoryMiddleware) ──
@app.get("/v1/memory")
async def memory_get(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    return await read_memory(uid)


@app.post("/v1/memory/write")
async def memory_write(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await _json(request)
    return JSONResponse(await write_memory(uid, body.get("content")))


# ── Workspace (PER-SESSION file browser + CRUD over the agent's working dir) ──
# Every route takes a thread_id and resolves it to the session's workspace_id
# (defaults to the thread_id; a forked chat shares its parent's) so the dock
# shows exactly the dir the agent reads/writes for that conversation.
async def _ws_id(request: Request, uid: str, thread_id) -> str:
    return await sessions_mod.workspace_id_for(uid, str(thread_id or ""))


@app.get("/v1/workspace/tree")
async def workspace_tree(request: Request):
    """The session's workspace file tree (the dir the agent reads/writes)."""
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    ws = await _ws_id(request, uid, request.query_params.get("thread_id"))
    return {"tree": workspace_mod.build_tree(settings, uid, ws)}


@app.get("/v1/workspace/file")
async def workspace_file(request: Request):
    """Read one workspace file (UTF-8 text; binary files are flagged)."""
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    ws = await _ws_id(request, uid, request.query_params.get("thread_id"))
    data = workspace_mod.read_file(settings, uid, ws, request.query_params.get("path") or "")
    if data is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(data)


@app.get("/v1/media")
async def media_get(request: Request):
    """Serve a local media file referenced by an absolute path (a chat ``MEDIA:``
    marker). Confined to the user's workspace / home / mounted drives, type- and
    size-checked. Used for imported conversations + the LLM's MEDIA convention."""
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    res = media_mod.resolve_media(settings, uid, request.query_params.get("path") or "")
    if res is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    full, mime = res
    if request.query_params.get("convert") == "pdf" and media_mod.is_office(full):
        pdf = await media_mod.office_to_pdf(full)
        if not pdf:
            return JSONResponse({"error": "conversion unavailable"}, status_code=502)
        return FileResponse(pdf, media_type="application/pdf")
    return FileResponse(full, media_type=mime)


@app.get("/v1/workspace/raw")
async def workspace_raw(request: Request):
    """Serve a workspace file's raw bytes (images, PDFs, downloads)."""
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    ws = await _ws_id(request, uid, request.query_params.get("thread_id"))
    res = workspace_mod.raw_file(settings, uid, ws, request.query_params.get("path") or "")
    if res is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    full, mime = res
    if request.query_params.get("convert") == "pdf" and media_mod.is_office(full):
        pdf = await media_mod.office_to_pdf(full)
        if not pdf:
            return JSONResponse({"error": "conversion unavailable"}, status_code=502)
        return FileResponse(pdf, media_type="application/pdf")
    return FileResponse(full, media_type=mime)


@app.post("/v1/workspace/save")
async def workspace_save(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await _json(request)
    ws = await _ws_id(request, uid, body.get("thread_id"))
    return JSONResponse(
        workspace_mod.save_file(settings, uid, ws, body.get("path"), body.get("content", ""))
    )


@app.post("/v1/workspace/mkdir")
async def workspace_mkdir(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await _json(request)
    ws = await _ws_id(request, uid, body.get("thread_id"))
    return JSONResponse(workspace_mod.make_dir(settings, uid, ws, body.get("path")))


@app.post("/v1/workspace/delete")
async def workspace_delete(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await _json(request)
    ws = await _ws_id(request, uid, body.get("thread_id"))
    return JSONResponse(workspace_mod.delete_path(settings, uid, ws, body.get("path")))


@app.post("/v1/workspace/rename")
async def workspace_rename(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await _json(request)
    ws = await _ws_id(request, uid, body.get("thread_id"))
    return JSONResponse(workspace_mod.rename_path(settings, uid, ws, body.get("from"), body.get("to")))


@app.post("/v1/workspace/upload")
async def workspace_upload(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    form = await request.form()
    up = form.get("file")
    if up is None or not hasattr(up, "read"):
        return JSONResponse({"ok": False, "error": "no file"}, status_code=400)
    data = await up.read()
    ws = await _ws_id(request, uid, form.get("thread_id"))
    return JSONResponse(
        workspace_mod.save_upload(
            settings, uid, ws, str(form.get("dir") or ""), getattr(up, "filename", "upload"), data
        )
    )


# ── Per-user UI settings (sidebar tab order). Dev → JSON file, prod → Postgres. ──
@app.get("/v1/settings/ui")
async def settings_ui_get(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    return await usersettings_mod.read_ui(uid)


@app.put("/v1/settings/ui")
async def settings_ui_put(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await _json(request)
    return JSONResponse(await usersettings_mod.write_ui(uid, body))


@app.get("/v1/skins")
async def skins_catalog(request: Request):
    """The shipped skin catalog (DB) for the Appearance picker."""
    verify_gateway_key(request, settings)
    return {"skins": await usersettings_mod.list_skins()}


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
    model = await resolve_model(settings, body.get("model"), user_id)  # passthrough (validated)
    thread_id = _thread_id(request, body)
    text = _last_user_text(body.get("messages") or [])
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
    model = await resolve_model(settings, body.get("model"), user_id)
    thread_id = _thread_id(request, body)
    text = _run_input_text(body)
    reasoning = body.get("reasoning_effort")
    if reasoning is None:
        reasoning = body.get("reasoning")
    ws_id = await sessions_mod.workspace_id_for(user_id, thread_id)
    ctx = AgentContext(user_id=user_id, thread_id=thread_id, workspace_id=ws_id)
    agent = await get_run_agent(settings, request.app.state.checkpointer, request.app.state.store, model, user_id, reasoning=reasoning)
    run_id = await runs_mod.start_run(agent, ctx, text)
    logger.info("run start id=%s user=%s thread=%s ws=%s model=%s reasoning=%s", run_id, user_id, thread_id, ws_id, model, reasoning)
    try:
        await sessions_mod.record_session(
            user_id, thread_id, first_text=text, model=model, reasoning=reasoning, workspace_id=ws_id
        )
    except Exception:  # noqa: BLE001
        logger.warning("record_session failed", exc_info=True)
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


# ── Sessions (conversation threads) — registry in the store, messages from the
# checkpointer. Per-user via X-User-Id. ──────────────────────────────────────
@app.get("/v1/sessions")
async def sessions_list(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    return {"sessions": await sessions_mod.list_sessions(uid)}


@app.post("/v1/sessions")
async def sessions_create(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    return JSONResponse(await sessions_mod.create_session(uid, body.get("title")))


@app.get("/v1/sessions/{thread_id}/messages")
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


@app.post("/v1/sessions/import")
async def sessions_import(request: Request):
    """Create a new conversation from an imported messages array."""
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await _json(request)
    agent = await get_run_agent(
        settings, request.app.state.checkpointer, request.app.state.store, await resolve_model(settings, None, uid), uid
    )
    return JSONResponse(
        await sessions_mod.import_session(
            agent, uid, body.get("messages") or [], body.get("title")
        )
    )


@app.patch("/v1/sessions/{thread_id}")
async def sessions_rename(thread_id: str, request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    return JSONResponse(
        await sessions_mod.rename_session(uid, thread_id, body.get("title", ""))
    )


@app.delete("/v1/sessions/{thread_id}")
async def sessions_delete(thread_id: str, request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    return JSONResponse(
        await sessions_mod.delete_session(
            request.app.state.checkpointer, uid, thread_id
        )
    )


# ── Serve the built React SPA (single-server / Phase 4) ──────────────────────
# FastAPI 0.138+'s `app.frontend()` serves the Vite `dist` as LOW-PRIORITY routes:
# the /v1 API, /static and favicons are matched first, and the frontend (hashed
# assets + index.html) only if nothing else matched. `fallback="auto"` returns
# index.html for unmatched client routes so /settings, /signin, … resolve on
# direct navigation / refresh. Gated on the build existing so dev (no dist) is fine.
_FRONTEND_DIST = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")
)
if os.path.isfile(os.path.join(_FRONTEND_DIST, "index.html")):
    app.frontend("/", directory=_FRONTEND_DIST, fallback="auto")
    logger.info("serving SPA from %s", _FRONTEND_DIST)
