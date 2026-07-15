"""Model registry + per-user Providers-tab CRUD (global models read-only)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.agent import xai_oauth
from app.agent.agent import (
    delete_user_model,
    describe_models,
    describe_providers,
    discover_models,
    merged_model_specs,
    model_supports_reasoning,
    save_user_model,
    save_user_models_bulk,
    test_model,
)
from app.core.auth import resolve_user_id, verify_gateway_key
from app.core.enums import Provider
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
                "capabilities": s.get("capabilities") or [],
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


@router.post("/v1/models/config/discover")
async def models_config_discover(request: Request):
    """List the models a provider's API exposes, from the credentials in the body, so
    the Providers tab can render them for selection instead of hand-typing a model id."""
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await json_body(request)
    return JSONResponse(await discover_models(settings, uid, body))


@router.post("/v1/models/config/save-bulk")
async def models_config_save_bulk(request: Request):
    """Save several discovered models at once (shared provider creds + one per id)."""
    verify_gateway_key(request, settings)
    uid = resolve_user_id(request, settings)
    body = await json_body(request)
    return JSONResponse(await save_user_models_bulk(settings, uid, body))


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


@router.post("/v1/models/config/xai-oauth/start")
async def xai_oauth_start(request: Request):
    """Kick off the xAI Grok device-code login (RFC 8628) — the Providers tab shows
    the returned ``user_code``/``verification_uri_complete`` and starts polling."""
    verify_gateway_key(request, settings)
    resolve_user_id(request, settings)  # auth-gated, but the flow itself isn't per-user yet
    try:
        data = await xai_oauth.request_device_code()
        return JSONResponse({
            "ok": True,
            "device_code": data.get("device_code"),
            "user_code": data.get("user_code"),
            "verification_uri": data.get("verification_uri"),
            "verification_uri_complete": data.get("verification_uri_complete"),
            "interval": data.get("interval") or 5,
            "expires_in": data.get("expires_in"),
        })
    except Exception as e:  # noqa: BLE001 — surface any failure to the UI
        return JSONResponse({"ok": False, "error": f"could not start xAI login: {e}"})


@router.post("/v1/models/config/xai-oauth/poll")
async def xai_oauth_poll(request: Request):
    """One poll attempt against the device-code token endpoint — the frontend calls
    this on its own ``interval`` timer rather than the backend blocking a connection
    open for the whole login. On ``"complete"`` the tokens are returned to the
    frontend so the normal discover → select → save-bulk flow can run next."""
    verify_gateway_key(request, settings)
    resolve_user_id(request, settings)
    body = await json_body(request)
    device_code = str(body.get("device_code") or "").strip()
    if not device_code:
        return JSONResponse({"status": "error", "error": "missing device_code"})
    try:
        return JSONResponse(await xai_oauth.poll_device_token(device_code))
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"status": "error", "error": str(e)[:300]})
