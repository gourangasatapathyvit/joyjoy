"""xAI (Grok) OAuth device-code client — RFC 8628 Device Authorization Grant.

Lets a user log in with a SuperGrok / X Premium+ subscription instead of a
paid-per-token API key. No redirect_uri is involved (that's the whole point of
the device-code grant), which is why this is the one xAI OAuth flow that
actually ports to a server backend: the Authorization-Code+PKCE flow other
xAI-integrating tools also support only works because it's pinned to a
loopback port that's pre-registered as an allowed redirect_uri for the
client_id below — joyjoy's own callback URL isn't on that allowlist and there
is no self-serve way to add one.

``CLIENT_ID`` is a PUBLIC client id for "Grok-CLI"-style OAuth integrations,
shared across independent open-source projects for exactly this purpose (not
a joyjoy-specific secret) — confirmed by cross-referencing two independent
existing implementations that both use the identical id/endpoints/scope.
"""

from __future__ import annotations

import base64
import json
import logging
import time
from urllib.parse import urlsplit

import httpx

logger = logging.getLogger("joyjoy.xai_oauth")

ISSUER = "https://auth.x.ai"
DISCOVERY_URL = f"{ISSUER}/.well-known/openid-configuration"
CLIENT_ID = "b1a00492-073a-47ea-816f-4c329264a828"
SCOPE = "openid profile email offline_access grok-cli:access api:access"
DEVICE_CODE_URL = f"{ISSUER}/oauth2/device/code"
DEVICE_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"

_TIMEOUT_S = 15.0
# Refresh this long before actual expiry, so a request never races an
# about-to-expire token. Access tokens are typically short-lived (hours).
REFRESH_SKEW_S = 300


def _is_xai_https(url: str) -> bool:
    """Refuse anything that isn't an HTTPS *.x.ai endpoint — the token
    endpoint comes from a live discovery fetch, so pin its origin instead of
    trusting whatever the response happens to contain."""
    try:
        p = urlsplit(url)
    except ValueError:
        return False
    return p.scheme == "https" and (p.hostname == "x.ai" or (p.hostname or "").endswith(".x.ai"))


async def _discover_token_endpoint() -> str:
    async with httpx.AsyncClient(timeout=_TIMEOUT_S) as c:
        r = await c.get(DISCOVERY_URL)
        r.raise_for_status()
        doc = r.json()
    endpoint = doc.get("token_endpoint") or ""
    if not _is_xai_https(endpoint):
        raise ValueError("xAI OAuth discovery returned an unexpected token_endpoint")
    return endpoint


async def request_device_code() -> dict:
    """Start the flow: returns the RFC 8628 device-code response — the caller
    shows ``user_code``/``verification_uri(_complete)`` to the user and polls
    with ``device_code`` at the given ``interval``."""
    async with httpx.AsyncClient(timeout=_TIMEOUT_S) as c:
        r = await c.post(
            DEVICE_CODE_URL,
            data={"client_id": CLIENT_ID, "scope": SCOPE},
            headers={"Accept": "application/json"},
        )
        r.raise_for_status()
        return r.json()


async def poll_device_token(device_code: str) -> dict:
    """One poll attempt (not a blocking loop — the route this backs is called
    repeatedly by the frontend on its own ``interval`` timer, matching the
    stateless-HTTP-server shape better than holding a connection open for
    minutes). Returns ``{"status": "pending"|"complete"|"expired"|"error", ...}``."""
    token_endpoint = await _discover_token_endpoint()
    async with httpx.AsyncClient(timeout=_TIMEOUT_S) as c:
        r = await c.post(
            token_endpoint,
            data={
                "grant_type": DEVICE_GRANT_TYPE,
                "device_code": device_code,
                "client_id": CLIENT_ID,
            },
            headers={"Accept": "application/json"},
        )
    if r.status_code == 200:
        data = r.json()
        return {
            "status": "complete",
            "access_token": data.get("access_token"),
            "refresh_token": data.get("refresh_token"),
            "expires_in": data.get("expires_in"),
        }
    try:
        err = (r.json() or {}).get("error") or ""
    except Exception:
        err = ""
    if err == "authorization_pending":
        return {"status": "pending"}
    if err == "slow_down":
        return {"status": "pending", "slow_down": True}
    if err in ("expired_token", "access_denied"):
        return {"status": "expired" if err == "expired_token" else "error", "error": err}
    return {"status": "error", "error": err or f"HTTP {r.status_code}"}


async def refresh_access_token(refresh_token: str) -> dict:
    """``grant_type=refresh_token`` — xAI rotates the refresh token on every
    use, so the caller MUST persist the new ``refresh_token`` this returns
    (the old one won't work a second time). Raises on failure — a 400/401/403
    here means the grant is dead (revoked or already-used-and-rotated) and the
    stored tokens should be treated as invalid, not silently ignored."""
    token_endpoint = await _discover_token_endpoint()
    async with httpx.AsyncClient(timeout=_TIMEOUT_S) as c:
        r = await c.post(
            token_endpoint,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": CLIENT_ID,
            },
            headers={"Accept": "application/json"},
        )
        r.raise_for_status()
        data = r.json()
    return {
        "access_token": data.get("access_token"),
        "refresh_token": data.get("refresh_token") or refresh_token,
        "expires_in": data.get("expires_in"),
    }


def _jwt_exp(token: str) -> int | None:
    """Best-effort, UNVERIFIED decode of a JWT's ``exp`` claim — only used to
    decide whether to proactively refresh, never to trust the token's
    contents (the actual request to xAI is what validates it)."""
    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        exp = payload.get("exp")
        return int(exp) if exp is not None else None
    except Exception:
        return None


def is_expiring(expires_at: float | None, access_token: str | None) -> bool:
    """True if the stored token is within ``REFRESH_SKEW_S`` of expiry (or its
    expiry can't be determined at all — refresh rather than risk a live 401)."""
    if expires_at:
        return time.time() >= (expires_at - REFRESH_SKEW_S)
    exp = _jwt_exp(access_token or "")
    if exp is not None:
        return time.time() >= (exp - REFRESH_SKEW_S)
    return True
