"""MCP servers + tools (read-only introspection) and per-user MCP CRUD
(global servers are read-only)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.agent.agent import delete_user_mcp, describe_mcp, save_user_mcp, toggle_user_mcp
from app.core.auth import resolve_user_id, verify_gateway_key
from .deps import json_body, settings

router = APIRouter()


@router.get("/v1/mcp/servers")
async def mcp_servers(request: Request):
    """Global + per-user MCP servers for the calling user (read-only; UI MCP tab)."""
    verify_gateway_key(request, settings)
    user_id = resolve_user_id(request, settings)
    servers, _tools = await describe_mcp(settings, user_id)
    return {"servers": servers, "toggle_supported": False}


@router.get("/v1/mcp/tools")
async def mcp_tools(request: Request):
    """Tools exposed by the user's global + per-user MCP servers (UI MCP tab)."""
    verify_gateway_key(request, settings)
    user_id = resolve_user_id(request, settings)
    _servers, tools = await describe_mcp(settings, user_id)
    return {"tools": tools, "total": len(tools)}


@router.put("/v1/mcp/servers/{name}")
async def mcp_server_save(name: str, request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await json_body(request)
    cfg = {k: body.get(k) for k in ("command", "args", "url", "headers", "env", "transport", "timeout", "enabled") if body.get(k) not in (None, "")}
    return JSONResponse(await save_user_mcp(settings, uid, name, cfg))


@router.delete("/v1/mcp/servers/{name}")
async def mcp_server_delete(name: str, request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    return JSONResponse(await delete_user_mcp(settings, uid, name))


@router.patch("/v1/mcp/servers/{name}")
async def mcp_server_toggle(name: str, request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await json_body(request)
    return JSONResponse(await toggle_user_mcp(settings, uid, name, bool(body.get("enabled"))))
