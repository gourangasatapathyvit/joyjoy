"""Per-session workspace file browser + CRUD (over the agent's working dir) and
the /v1/media file server. Every route resolves the thread_id to the session's
workspace_id so the dock mirrors exactly what the agent reads/writes.

When ``settings.sandbox_enabled`` the dir lives inside the per-session OpenSandbox
volume → ops route to the async ``workspace_sandbox`` facade; otherwise they use
the host ``workspace`` module (in a worker thread). Both return the same shapes.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse, Response

from app.workspace import media as media_mod
from app.sandbox import sandbox as sandbox_mgr
from app.stores import sessions as sessions_mod
from app.workspace import workspace as workspace_mod
from app.sandbox import workspace_sandbox as ws_sbx
from app.core.auth import current_user_id, resolve_user_id, verify_gateway_key
from app.core.constants import MAX_UPLOAD_BYTES
from .deps import json_body, settings

router = APIRouter()


def _sbx() -> bool:
    return sandbox_mgr.is_enabled(settings)


def _norm_path(p: str | None) -> str:
    """Normalize an incoming workspace path before it reaches either backend.

    Tolerates absolute mount-prefixed paths (``/workspace/foo``) as
    workspace-relative (``foo``). The agent records absolute mount paths in its
    write_file/edit_file tool-call args whenever the sandbox prompt sets its cwd
    to the mount; those reach the dock/media layer verbatim. Stripping the prefix
    here fixes BOTH backends: the sandbox facade (else ``_abs`` doubles it →
    ``/workspace/workspace/foo``) AND the host resolver (else ``os.path.join``
    treats the leading ``/`` as absolute, escaping the root → confinement 404)."""
    mount = (settings.sandbox_mount_path or "/workspace").rstrip("/")
    p = str(p or "").strip()
    if p == mount:
        return ""
    if p.startswith(mount + "/"):
        return p[len(mount) + 1 :]
    return p


async def _ws_id(uid: str, thread_id) -> str:
    return await sessions_mod.workspace_id_for(uid, str(thread_id or ""))


@router.get("/v1/workspace/tree")
async def workspace_tree(request: Request):
    """The session's workspace file tree (the dir the agent reads/writes)."""
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    ws = await _ws_id(uid, request.query_params.get("thread_id"))
    if _sbx():
        return {"tree": await ws_sbx.tree(settings, ws)}
    return {"tree": await asyncio.to_thread(workspace_mod.build_tree, settings, uid, ws)}


@router.get("/v1/workspace/file")
async def workspace_file(request: Request):
    """Read one workspace file (UTF-8 text; binary files are flagged)."""
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    ws = await _ws_id(uid, request.query_params.get("thread_id"))
    path = _norm_path(request.query_params.get("path"))
    data = (
        await ws_sbx.read_file(settings, ws, path)
        if _sbx()
        else await asyncio.to_thread(workspace_mod.read_file, settings, uid, ws, path)
    )
    if data is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(data)


@router.get("/v1/media")
async def media_get(request: Request):
    """Serve a chat ``MEDIA:`` marker's bytes. When the sandbox is enabled the file
    lives in the session's sandbox volume (resolved like /v1/workspace/raw, by
    thread_id); otherwise it's a host path (imported convos / the LLM's MEDIA
    convention), resolved under the per-user workspace root."""
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    raw_path = request.query_params.get("path") or ""
    if _sbx():
        # Sandbox mode: every workspace op is in the sandbox — stream from the volume.
        ws = await _ws_id(uid, request.query_params.get("thread_id"))
        res = await ws_sbx.raw_file(settings, ws, _norm_path(raw_path))
        if res is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        data, mime = res
        return Response(content=data, media_type=mime)
    res = media_mod.resolve_media(settings, uid, raw_path)
    if res is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    full, mime = res
    if request.query_params.get("convert") == "pdf" and media_mod.is_office(full):
        pdf = await media_mod.office_to_pdf(full)
        if not pdf:
            return JSONResponse({"error": "conversion unavailable"}, status_code=502)
        return FileResponse(pdf, media_type="application/pdf")
    return FileResponse(full, media_type=mime)


@router.get("/v1/workspace/raw")
async def workspace_raw(request: Request):
    """Serve a workspace file's raw bytes (images, PDFs, downloads)."""
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    ws = await _ws_id(uid, request.query_params.get("thread_id"))
    path = _norm_path(request.query_params.get("path"))
    want_pdf = request.query_params.get("convert") == "pdf"
    if _sbx():
        # Sandbox files have no host path → stream bytes directly. (Office→PDF
        # preview conversion is host-only; sandbox serves the raw bytes.)
        res = await ws_sbx.raw_file(settings, ws, path)
        if res is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        data, mime = res
        return Response(content=data, media_type=mime)
    res = workspace_mod.raw_file(settings, uid, ws, path)
    if res is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    full, mime = res
    if want_pdf and media_mod.is_office(full):
        pdf = await media_mod.office_to_pdf(full)
        if not pdf:
            return JSONResponse({"error": "conversion unavailable"}, status_code=502)
        return FileResponse(pdf, media_type="application/pdf")
    return FileResponse(full, media_type=mime)


@router.get("/v1/workspace/download")
async def workspace_download(request: Request):
    """Download a workspace entry as an attachment: a single file as-is, or a folder
    (or the whole workspace) zipped. Requires a SIGNED-IN user — unlike the other
    workspace routes there is NO dev fallback identity, so a signed-out client (no
    session) gets 401 and cannot download."""
    verify_gateway_key(request, settings)
    uid = current_user_id(request, settings)
    if not uid:
        return JSONResponse({"error": "sign in required"}, status_code=401)
    ws = await _ws_id(uid, request.query_params.get("thread_id"))
    path = _norm_path(request.query_params.get("path"))
    res = (
        await ws_sbx.download(settings, ws, path)
        if _sbx()
        else await asyncio.to_thread(workspace_mod.download, settings, uid, ws, path)
    )
    if res is None:
        return JSONResponse({"error": "not found or too large"}, status_code=404)
    data, mime, filename = res
    safe_name = filename.replace('"', "")
    return Response(
        content=data,
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )


@router.post("/v1/workspace/save")
async def workspace_save(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await json_body(request)
    ws = await _ws_id(uid, body.get("thread_id"))
    path, content = _norm_path(body.get("path")), body.get("content", "")
    res = (
        await ws_sbx.save_file(settings, ws, path, content)
        if _sbx()
        else await asyncio.to_thread(workspace_mod.save_file, settings, uid, ws, path, content)
    )
    return JSONResponse(res)


@router.post("/v1/workspace/mkdir")
async def workspace_mkdir(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await json_body(request)
    ws = await _ws_id(uid, body.get("thread_id"))
    path = _norm_path(body.get("path"))
    res = (
        await ws_sbx.make_dir(settings, ws, path)
        if _sbx()
        else await asyncio.to_thread(workspace_mod.make_dir, settings, uid, ws, path)
    )
    return JSONResponse(res)


@router.post("/v1/workspace/delete")
async def workspace_delete(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await json_body(request)
    ws = await _ws_id(uid, body.get("thread_id"))
    path = _norm_path(body.get("path"))
    res = (
        await ws_sbx.delete_path(settings, ws, path)
        if _sbx()
        else await asyncio.to_thread(workspace_mod.delete_path, settings, uid, ws, path)
    )
    return JSONResponse(res)


@router.post("/v1/workspace/rename")
async def workspace_rename(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await json_body(request)
    ws = await _ws_id(uid, body.get("thread_id"))
    src, dst = _norm_path(body.get("from")), _norm_path(body.get("to"))
    res = (
        await ws_sbx.rename_path(settings, ws, src, dst)
        if _sbx()
        else await asyncio.to_thread(workspace_mod.rename_path, settings, uid, ws, src, dst)
    )
    return JSONResponse(res)


@router.post("/v1/workspace/upload")
async def workspace_upload(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    form = await request.form()
    up = form.get("file")
    if up is None or not hasattr(up, "read"):
        return JSONResponse({"ok": False, "error": "no file"}, status_code=400)
    data = await up.read()
    if len(data) > MAX_UPLOAD_BYTES:
        return JSONResponse({"ok": False, "error": "file too large"}, status_code=413)
    ws = await _ws_id(uid, form.get("thread_id"))
    dir_rel, filename = _norm_path(form.get("dir")), getattr(up, "filename", "upload")
    res = (
        await ws_sbx.save_upload(settings, ws, dir_rel, filename, data)
        if _sbx()
        else await asyncio.to_thread(workspace_mod.save_upload, settings, uid, ws, dir_rel, filename, data)
    )
    return JSONResponse(res)
