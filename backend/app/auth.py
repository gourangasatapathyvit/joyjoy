"""Authentication helpers.

- ``verify_gateway_key`` — optional shared-key check for a fronting tier (no-op
  when ``GATEWAY_API_KEY`` is unset, which is the single-server default).
- Identity resolution for tenant isolation, in priority order:
  ``X-User-Id`` header (dev proxy) > signed **session cookie** (real login) >
  ``Authorization: Bearer`` JWT (direct clients) > dev default.
  The identity is the user's surrogate uuid (``User.id``), carried in the cookie
  ``sub``. ``current_user_id`` does the same WITHOUT the dev fallback — it backs
  ``/v1/auth/me`` and the login gate so an unauthenticated visitor is a real 401.
- Session tokens are short JWTs signed with ``JWT_SECRET``, set as an httpOnly
  cookie by the ``/v1/auth/*`` routes.
"""

from __future__ import annotations

import time

import jwt
from fastapi import HTTPException, Request

from .config import Settings


def _bearer(request: Request) -> str:
    h = request.headers.get("authorization", "")
    return h[7:].strip() if h[:7].lower() == "bearer " else ""


def verify_gateway_key(request: Request, settings: Settings) -> None:
    if not settings.gateway_api_key:
        return  # open when no key is configured (single-server default)
    provided = request.headers.get("x-api-key") or _bearer(request)
    if provided != settings.gateway_api_key:
        raise HTTPException(status_code=401, detail="invalid gateway api key")


# ── Session cookie (signed JWT; sub = User.id) ───────────────────────────────
def make_session_token(settings: Settings, user_id: str) -> str:
    now = int(time.time())
    return jwt.encode(
        {"sub": str(user_id), "iat": now, "exp": now + settings.session_ttl_hours * 3600},
        settings.jwt_secret,
        algorithm="HS256",
    )


def read_session_user_id(settings: Settings, request: Request) -> str | None:
    tok = request.cookies.get(settings.session_cookie)
    if not tok or not settings.jwt_secret:
        return None
    try:
        return jwt.decode(tok, settings.jwt_secret, algorithms=["HS256"]).get("sub")
    except Exception:
        return None


def _bearer_sub(settings: Settings, request: Request) -> str | None:
    token = _bearer(request)
    if not token or not settings.jwt_secret:
        return None
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[a.strip() for a in settings.jwt_algorithms.split(",") if a.strip()],
            audience=settings.jwt_audience or None,
            options={"verify_aud": bool(settings.jwt_audience)},
        )
    except Exception:
        return None
    sub = claims.get("sub") or claims.get("user_id")
    return str(sub) if sub else None


def current_user_id(request: Request, settings: Settings) -> str | None:
    """Authenticated identity (User.id) with NO dev fallback — for /v1/auth/me
    and gating."""
    # The X-User-Id header is only trusted from a trusted caller: dev, or when a
    # gateway API key is configured (verify_gateway_key validates it upstream on
    # the same request). In prod with NO gateway key the header is ignored — else
    # any client could impersonate any user by setting it. Identity then comes
    # from the signed session cookie / bearer JWT only.
    if not settings.is_prod or settings.gateway_api_key:
        uid = request.headers.get(settings.user_id_header.lower())
        if uid:
            return uid.strip()
    sess = read_session_user_id(settings, request)
    if sess:
        return sess
    return _bearer_sub(settings, request)


def resolve_user_id(request: Request, settings: Settings) -> str:
    u = current_user_id(request, settings)
    if u:
        return u
    if not settings.is_prod:
        from .users import DEV_USER_ID  # lazy: avoids import cycle

        return DEV_USER_ID
    raise HTTPException(status_code=401, detail="missing user identity (session or JWT)")
