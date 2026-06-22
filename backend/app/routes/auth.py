"""Auth: username/password accounts, signed session cookie, email-OTP reset."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .. import users as users_mod
from ..auth import current_user_id, make_session_token
from .deps import json_body, settings

router = APIRouter(prefix="/v1/auth")


def _set_session(resp: JSONResponse, user_id: str) -> JSONResponse:
    resp.set_cookie(
        settings.session_cookie,
        make_session_token(settings, user_id),
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        samesite="lax",
        secure=settings.is_prod,  # require HTTPS only in prod
        path="/",
    )
    return resp


@router.post("/signup")
async def auth_signup(request: Request):
    body = await json_body(request)
    res = await users_mod.create_user(body.get("username"), body.get("email"), body.get("password"))
    if not res.get("ok"):
        return JSONResponse(res, status_code=409 if res.get("field") in ("username", "email") else 400)
    user = res["user"]
    return _set_session(JSONResponse({"ok": True, "user": user}), user["id"])


@router.post("/login")
async def auth_login(request: Request):
    body = await json_body(request)
    user = await users_mod.verify_credentials(body.get("username"), body.get("password"))
    if not user:
        return JSONResponse({"ok": False, "error": "Invalid username or password."}, status_code=401)
    return _set_session(JSONResponse({"ok": True, "user": user}), user["id"])


@router.post("/logout")
async def auth_logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(settings.session_cookie, path="/")
    return resp


@router.get("/me")
async def auth_me(request: Request):
    uid = current_user_id(request, settings)
    if not uid:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)
    rec = await users_mod.get_user_by_id(uid)
    if not rec:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)
    return {"username": rec["username"], "email": rec.get("email")}


@router.get("/available")
async def auth_available(request: Request):
    """Live signup validation: is this username / email already taken?"""
    q = request.query_params
    out: dict = {}
    if q.get("username"):
        out["username_taken"] = await users_mod.username_taken(q["username"])
    if q.get("email"):
        out["email_taken"] = await users_mod.email_taken(q["email"])
    return out


@router.post("/forgot")
async def auth_forgot(request: Request):
    """Email a reset OTP. Always returns ok (never reveals whether the email exists)."""
    body = await json_body(request)
    email = body.get("email") or ""
    out: dict = {"ok": True}
    res = await users_mod.create_reset_otp(settings, email)
    if res:
        otp, _user_id = res
        emailed = await users_mod.send_otp_email(settings, email, otp)
        if not emailed and not settings.is_prod:
            out["dev_otp"] = otp  # dev convenience when SMTP isn't configured
    return JSONResponse(out)


@router.post("/reset")
async def auth_reset(request: Request):
    body = await json_body(request)
    if not users_mod.valid_password(body.get("password") or ""):
        return JSONResponse({"ok": False, "error": "Password must be at least 8 characters."}, status_code=400)
    res = await users_mod.verify_and_consume_otp(body.get("email"), body.get("otp"))
    if not res.get("ok"):
        return JSONResponse(res, status_code=400)
    await users_mod.set_password(res["user_id"], body.get("password"))
    return _set_session(JSONResponse({"ok": True}), res["user_id"])  # auto-login after reset


@router.post("/change-password")
async def auth_change_password(request: Request):
    uid = current_user_id(request, settings)
    if not uid:
        return JSONResponse({"ok": False, "error": "Not signed in."}, status_code=401)
    body = await json_body(request)
    res = await users_mod.change_password(uid, body.get("current") or "", body.get("new") or "")
    return JSONResponse(res, status_code=200 if res.get("ok") else 400)
