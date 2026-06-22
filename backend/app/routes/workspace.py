"""Per-session workspace file browser + CRUD (over the agent's working dir) and
the /v1/media file server. Every route resolves the thread_id to the session's
workspace_id so the dock mirrors exactly what the agent reads/writes."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse

from .. import media as media_mod
from .. import sessions as sessions_mod
from .. import workspace as workspace_mod
from ..auth import resolve_user_id, verify_gateway_key
from ..constants import MAX_UPLOAD_BYTES
from .deps import json_body, settings

router = APIRouter()


async def _ws_id(uid: str, thread_id) -> str:
    return await sessions_mod.workspace_id_for(uid, str(thread_id or ""))


@router.get("/v1/workspace/tree")
async def workspace_tree(request: Request):
    """The session's workspace file tree (the dir the agent reads/writes)."""
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    ws = await _ws_id(uid, request.query_params.get("thread_id"))
    # Filesystem walk/IO runs in a worker thread so it never blocks the loop.
    return {"tree": await asyncio.to_thread(workspace_mod.build_tree, settings, uid, ws)}


@router.get("/v1/workspace/file")
async def workspace_file(request: Request):
    """Read one workspace file (UTF-8 text; binary files are flagged)."""
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    ws = await _ws_id(uid, request.query_params.get("thread_id"))
    data = await asyncio.to_thread(
        workspace_mod.read_file, settings, uid, ws, request.query_params.get("path") or ""
    )
    if data is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(data)


@router.get("/v1/media")
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


@router.get("/v1/workspace/raw")
async def workspace_raw(request: Request):
    """Serve a workspace file's raw bytes (images, PDFs, downloads)."""
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    ws = await _ws_id(uid, request.query_params.get("thread_id"))
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


@router.post("/v1/workspace/save")
async def workspace_save(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await json_body(request)
    ws = await _ws_id(uid, body.get("thread_id"))
    return JSONResponse(
        await asyncio.to_thread(
            workspace_mod.save_file, settings, uid, ws, body.get("path"), body.get("content", "")
        )
    )


@router.post("/v1/workspace/mkdir")
async def workspace_mkdir(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await json_body(request)
    ws = await _ws_id(uid, body.get("thread_id"))
    return JSONResponse(await asyncio.to_thread(workspace_mod.make_dir, settings, uid, ws, body.get("path")))


@router.post("/v1/workspace/delete")
async def workspace_delete(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await json_body(request)
    ws = await _ws_id(uid, body.get("thread_id"))
    return JSONResponse(await asyncio.to_thread(workspace_mod.delete_path, settings, uid, ws, body.get("path")))


@router.post("/v1/workspace/rename")
async def workspace_rename(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await json_body(request)
    ws = await _ws_id(uid, body.get("thread_id"))
    return JSONResponse(
        await asyncio.to_thread(workspace_mod.rename_path, settings, uid, ws, body.get("from"), body.get("to"))
    )


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
    return JSONResponse(
        await asyncio.to_thread(
            workspace_mod.save_upload,
            settings, uid, ws, str(form.get("dir") or ""), getattr(up, "filename", "upload"), data,
        )
    )
