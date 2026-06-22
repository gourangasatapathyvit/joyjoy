"""Health / heartbeat endpoints (gateway liveness)."""

from __future__ import annotations

from fastapi import APIRouter

from .deps import settings

router = APIRouter()


def _health_payload() -> dict:
    return {
        "status": "ok",
        "state": "alive",
        "gateway_state": "alive",
        "env": settings.app_env,
        "prod": settings.is_prod,
        "models": list(settings.model_specs),
    }


@router.get("/healthz")
async def healthz():
    return _health_payload()


@router.get("/health")
async def health():
    return _health_payload()


@router.get("/health/detailed")
async def health_detailed():
    return _health_payload()


@router.get("/v1/health")
async def v1_health():
    return _health_payload()
