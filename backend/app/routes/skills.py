"""Skills introspection + per-user skill CRUD, incl. multi-file skills and zip
import (global skills are read-only)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..agent import (
    delete_user_skill,
    delete_user_skill_file,
    import_user_skill,
    list_skills,
    read_skill_content,
    save_user_skill,
    save_user_skill_file,
    toggle_user_skill,
)
from ..auth import resolve_user_id, verify_gateway_key
from .deps import json_body, settings

router = APIRouter()


@router.get("/v1/skills")
async def skills(request: Request):
    """Global skills (read-only) + per-user skills for the calling user (UI Skills tab)."""
    verify_gateway_key(request, settings)
    user_id = resolve_user_id(request, settings)
    items = await list_skills(settings, user_id)
    return {"skills": items}


@router.get("/v1/skills/content")
async def skill_content(request: Request):
    """Read-only content of one skill (SKILL.md or a linked file) for the UI viewer."""
    verify_gateway_key(request, settings)
    user_id = resolve_user_id(request, settings)
    name = request.query_params.get("name") or ""
    file = request.query_params.get("file") or None
    data = await read_skill_content(settings, user_id, name, file)
    return JSONResponse(data)


@router.post("/v1/skills/save")
async def skills_save(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await json_body(request)
    return JSONResponse(await save_user_skill(uid, body.get("name"), body.get("content")))


@router.post("/v1/skills/delete")
async def skills_delete(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await json_body(request)
    return JSONResponse(await delete_user_skill(uid, body.get("name")))


@router.post("/v1/skills/toggle")
async def skills_toggle(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await json_body(request)
    return JSONResponse(await toggle_user_skill(uid, body.get("name"), bool(body.get("enabled"))))


@router.post("/v1/skills/files/save")
async def skills_file_save(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await json_body(request)
    return JSONResponse(
        await save_user_skill_file(
            uid, body.get("skill"), body.get("path"), body.get("content") or "", body.get("encoding") or "utf-8"
        )
    )


@router.post("/v1/skills/files/delete")
async def skills_file_delete(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await json_body(request)
    return JSONResponse(await delete_user_skill_file(uid, body.get("skill"), body.get("path")))


@router.post("/v1/skills/import")
async def skills_import(request: Request):
    """Create/replace a user skill from a base64-encoded zip ({name, zip_b64})."""
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await json_body(request)
    return JSONResponse(await import_user_skill(uid, body.get("name"), body.get("zip_b64")))
