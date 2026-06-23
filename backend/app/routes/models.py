"""Model registry + per-user Providers-tab CRUD (global models read-only)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..agent import (
    delete_user_model,
    describe_models,
    describe_providers,
    merged_model_specs,
    model_supports_reasoning,
    save_user_model,
    test_model,
)
from ..auth import resolve_user_id, verify_gateway_key
from ..enums import Provider
from .deps import json_body, settings

router = APIRouter()


@router.get("/v1/models")
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
                "provider": s.get("provider", Provider.AZURE_OPENAI),
                "supports_reasoning": model_supports_reasoning(s),
            }
            for mid, s in specs.items()
        ],
    }


@router.get("/v1/models/config")
async def models_config(request: Request):
    """Global (read-only) + per-user models for the Providers tab, plus the
    provider field-schema the UI renders its add/edit forms from. Keys are masked."""
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    return {"models": await describe_models(settings, uid), "providers": await describe_providers()}


@router.post("/v1/models/config/save")
async def models_config_save(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await json_body(request)
    return JSONResponse(await save_user_model(settings, uid, body))


@router.post("/v1/models/config/delete")
async def models_config_delete(request: Request):
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await json_body(request)
    return JSONResponse(await delete_user_model(settings, uid, body.get("id")))


@router.post("/v1/models/config/test")
async def models_config_test(request: Request):
    """Live probe for the Providers-tab status lights: does this model answer a
    standard call, and does it produce (visible) reasoning? Two small real requests."""
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await json_body(request)
    model_id = body.get("id") or body.get("model")
    return JSONResponse(await test_model(settings, uid, model_id))
