"""Per-user memory: the always-loaded AGENTS.md (deepagents MemoryMiddleware) and
the dynamic /memories/ files (LangGraph store)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.agent.agent import (
    delete_memory_file,
    list_memory_files,
    read_memory,
    read_memory_file,
    toggle_memory_file,
    write_memory,
    write_memory_file,
)
from app.core.auth import resolve_user_id, verify_gateway_key
from .deps import json_body, settings

router = APIRouter()


@router.get("/v1/memory")
async def memory_get(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    return await read_memory(uid)


@router.post("/v1/memory/write")
async def memory_write(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await json_body(request)
    return JSONResponse(await write_memory(uid, body.get("content")))


@router.get("/v1/memories")
async def memories_list(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    return {"files": await list_memory_files(request.app.state.store, uid)}


@router.get("/v1/memories/file")
async def memories_read(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    path = request.query_params.get("path", "")
    return await read_memory_file(request.app.state.store, uid, path)


@router.post("/v1/memories/file")
async def memories_write(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await json_body(request)
    return JSONResponse(
        await write_memory_file(request.app.state.store, uid, body.get("path"), body.get("content"))
    )


@router.post("/v1/memories/delete")
async def memories_delete(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await json_body(request)
    return JSONResponse(await delete_memory_file(request.app.state.store, uid, body.get("path")))


@router.post("/v1/memories/toggle")
async def memories_toggle(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await json_body(request)
    return JSONResponse(
        await toggle_memory_file(request.app.state.store, uid, body.get("path"), bool(body.get("enabled")))
    )
