"""Per-user UI settings (sidebar tab order) + the shipped skin catalog."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.stores import usersettings as usersettings_mod
from app.core.auth import resolve_user_id, verify_gateway_key
from .deps import json_body, settings

router = APIRouter()


@router.get("/v1/settings/ui")
async def settings_ui_get(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    return await usersettings_mod.read_ui(uid)


@router.put("/v1/settings/ui")
async def settings_ui_put(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await json_body(request)
    return JSONResponse(await usersettings_mod.write_ui(uid, body))


@router.get("/v1/skins")
async def skins_catalog(request: Request):
    """The shipped skin catalog (DB) for the Appearance picker."""
    verify_gateway_key(request, settings)
    return {"skins": await usersettings_mod.list_skins()}
