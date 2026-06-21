"""User accounts + password-reset OTP.

Accounts (bcrypt-hashed password, email) live in the LangGraph store — the same
sqlite(dev)/Postgres(prod) backing as sessions/settings/memory — so no extra DB
wiring. Usernames are canonicalised to lowercase and ARE the tenant ``user_id``
used everywhere else. Password reset uses a hashed, expiring, single-use email OTP
(emailed via SMTP when configured; logged in dev otherwise).
"""

from __future__ import annotations

import asyncio
import logging
import re
import secrets
import smtplib
import time
from email.message import EmailMessage
from typing import Any

import bcrypt

logger = logging.getLogger("joyjoy.users")

_USERS = ("_auth", "users")  # username(lower) -> {username,email,password_hash,created_at}
_EMAILS = ("_auth", "emails")  # email(lower)   -> username(lower)   (uniqueness + lookup)
_OTPS = ("_auth", "otps")  # email(lower)       -> {hash,exp,attempts}

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9._-]{3,32}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_OTP_MAX_ATTEMPTS = 5


def _nu(u: str | None) -> str:
    return (u or "").strip().lower()


def _ne(e: str | None) -> str:
    return (e or "").strip().lower()


def valid_username(u: str | None) -> bool:
    return bool(_USERNAME_RE.match((u or "").strip()))


def valid_email(e: str | None) -> bool:
    return bool(_EMAIL_RE.match((e or "").strip()))


def valid_password(p: Any) -> bool:
    return isinstance(p, str) and len(p) >= 8


# ── bcrypt (≤72 bytes is bcrypt's input limit; slice avoids a ValueError) ──
def hash_pw(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8")[:72], bcrypt.gensalt()).decode("ascii")


def verify_pw(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode("utf-8")[:72], (hashed or "").encode("ascii"))
    except Exception:
        return False


def _val(item) -> dict | None:
    v = getattr(item, "value", None)
    return dict(v) if isinstance(v, dict) else None


# ── User CRUD ──────────────────────────────────────────────────────────────
async def get_user(store, username: str) -> dict | None:
    try:
        return _val(await store.aget(_USERS, _nu(username)))
    except Exception:
        logger.debug("get_user failed", exc_info=True)
        return None


async def username_taken(store, username: str) -> bool:
    return (await get_user(store, username)) is not None


async def email_taken(store, email: str) -> bool:
    try:
        return getattr(await store.aget(_EMAILS, _ne(email)), "value", None) is not None
    except Exception:
        return False


async def create_user(store, username: str, email: str, password: str) -> dict:
    """Create an account. Returns {ok:True, user} or {ok:False, error, field?}."""
    if not valid_username(username):
        return {"ok": False, "error": "Username must be 3–32 characters (letters, numbers, . _ -).", "field": "username"}
    if not valid_email(email):
        return {"ok": False, "error": "Enter a valid email address.", "field": "email"}
    if not valid_password(password):
        return {"ok": False, "error": "Password must be at least 8 characters.", "field": "password"}
    if await username_taken(store, username):
        return {"ok": False, "error": "That username is already taken.", "field": "username"}
    if await email_taken(store, email):
        return {"ok": False, "error": "An account with that email already exists.", "field": "email"}
    uid, em = _nu(username), _ne(email)
    rec = {"username": uid, "email": em, "password_hash": hash_pw(password), "created_at": time.time()}
    await store.aput(_USERS, uid, rec)
    await store.aput(_EMAILS, em, uid)
    return {"ok": True, "user": {"username": uid, "email": em}}


async def verify_credentials(store, username: str, password: str) -> dict | None:
    rec = await get_user(store, username)
    if not rec or not verify_pw(password, rec.get("password_hash", "")):
        return None
    return {"username": rec["username"], "email": rec.get("email")}


async def set_password(store, username: str, new_password: str) -> bool:
    rec = await get_user(store, username)
    if not rec:
        return False
    rec["password_hash"] = hash_pw(new_password)
    await store.aput(_USERS, _nu(username), rec)
    return True


async def change_password(store, username: str, current: str, new: str) -> dict:
    if not valid_password(new):
        return {"ok": False, "error": "New password must be at least 8 characters."}
    rec = await get_user(store, username)
    if not rec or not verify_pw(current, rec.get("password_hash", "")):
        return {"ok": False, "error": "Current password is incorrect."}
    await set_password(store, username, new)
    return {"ok": True}


# ── Password-reset OTP ───────────────────────────────────────────────────────
async def create_reset_otp(store, settings, email: str) -> tuple[str, str] | None:
    """Generate + store a hashed, expiring OTP. Returns (otp, username) if the
    email is registered, else None (caller stays silent either way)."""
    em = _ne(email)
    try:
        username = getattr(await store.aget(_EMAILS, em), "value", None)
    except Exception:
        username = None
    if not username:
        return None
    otp = f"{secrets.randbelow(1_000_000):06d}"
    await store.aput(
        _OTPS,
        em,
        {"hash": hash_pw(otp), "exp": time.time() + settings.otp_ttl_minutes * 60, "attempts": 0},
    )
    return otp, username


async def verify_and_consume_otp(store, email: str, otp: str) -> dict:
    em = _ne(email)
    try:
        rec = _val(await store.aget(_OTPS, em))
    except Exception:
        rec = None
    if not rec:
        return {"ok": False, "error": "No reset code requested — request a new one."}
    if time.time() > rec.get("exp", 0):
        await store.adelete(_OTPS, em)
        return {"ok": False, "error": "Reset code expired — request a new one."}
    if rec.get("attempts", 0) >= _OTP_MAX_ATTEMPTS:
        await store.adelete(_OTPS, em)
        return {"ok": False, "error": "Too many attempts — request a new code."}
    if not verify_pw(str(otp or ""), rec.get("hash", "")):
        rec["attempts"] = rec.get("attempts", 0) + 1
        await store.aput(_OTPS, em, rec)
        return {"ok": False, "error": "Incorrect code."}
    await store.adelete(_OTPS, em)
    try:
        username = getattr(await store.aget(_EMAILS, em), "value", None)
    except Exception:
        username = None
    if not username:
        return {"ok": False, "error": "Account not found."}
    return {"ok": True, "username": username}


# ── Email (SMTP when configured; dev logs the OTP) ───────────────────────────
def _send_email_sync(settings, to_addr: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as s:
        if settings.smtp_starttls:
            s.starttls()
        if settings.smtp_user:
            s.login(settings.smtp_user, settings.smtp_password)
        s.send_message(msg)


async def send_otp_email(settings, email: str, otp: str) -> bool:
    """Email the OTP. Returns True if actually sent. When SMTP isn't configured
    it logs the OTP (dev) and returns False."""
    app = settings.app_public_name
    subject = f"{app} password reset code"
    body = (
        f"Your {app} password reset code is: {otp}\n\n"
        f"It expires in {settings.otp_ttl_minutes} minutes. "
        f"If you didn't request this, you can ignore this email."
    )
    if not settings.smtp_host:
        logger.warning("[DEV] password-reset OTP for %s: %s (SMTP not configured)", email, otp)
        return False
    try:
        await asyncio.to_thread(_send_email_sync, settings, email, subject, body)
        logger.info("sent password-reset OTP email to %s", email)
        return True
    except Exception:
        logger.warning("OTP email send failed for %s", email, exc_info=True)
        return False
