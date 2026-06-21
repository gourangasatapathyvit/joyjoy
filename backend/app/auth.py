"""Authentication helpers.

Two independent checks:

1. ``verify_gateway_key`` — confirms the *caller* (hermes-webui) is allowed to
   use the gateway. Uses a shared API key (``X-API-Key`` or ``Authorization:
   Bearer``). Disabled when ``GATEWAY_API_KEY`` is unset (dev convenience).
2. ``resolve_user_id`` — extracts the *end user* identity for tenant isolation.
   Priority: explicit ``X-User-Id`` header (hermes forwards the authenticated
   user) > JWT ``sub`` (direct clients) > dev default.
"""

from __future__ import annotations

import jwt
from fastapi import HTTPException, Request

from .config import Settings


def _bearer(request: Request) -> str:
    h = request.headers.get("authorization", "")
    return h[7:].strip() if h[:7].lower() == "bearer " else ""


def verify_gateway_key(request: Request, settings: Settings) -> None:
    if not settings.gateway_api_key:
        return  # open in dev when no key is configured
    provided = request.headers.get("x-api-key") or _bearer(request)
    if provided != settings.gateway_api_key:
        raise HTTPException(status_code=401, detail="invalid gateway api key")


def resolve_user_id(request: Request, settings: Settings) -> str:
    # 1) explicit forwarded identity (preferred; set by a proxy / the dev Vite server)
    uid = request.headers.get(settings.user_id_header.lower())
    if uid:
        return uid.strip()

    # 2) same-origin SPA cookie. When FastAPI serves the built SPA itself (single-
    #    server / Phase 4) there's no forwarding proxy and EventSource can't send a
    #    header — the app sets a `joyjoy_uid` cookie on sign-in, sent on every
    #    same-origin fetch *and* the SSE stream.
    cookie_uid = request.cookies.get("joyjoy_uid")
    if cookie_uid:
        return cookie_uid.strip()

    # 3) JWT subject (direct clients / production without a forwarding proxy)
    token = _bearer(request)
    if token and settings.jwt_secret:
        try:
            claims = jwt.decode(
                token,
                settings.jwt_secret,
                algorithms=[a.strip() for a in settings.jwt_algorithms.split(",") if a.strip()],
                audience=settings.jwt_audience or None,
                options={"verify_aud": bool(settings.jwt_audience)},
            )
        except Exception as exc:  # noqa: BLE001 - surface as 401
            raise HTTPException(status_code=401, detail=f"invalid token: {exc}") from exc
        sub = claims.get("sub") or claims.get("user_id")
        if sub:
            return str(sub)

    # 4) dev fallback
    if not settings.is_prod:
        return settings.dev_default_user

    raise HTTPException(status_code=401, detail="missing user identity (X-User-Id or JWT)")
