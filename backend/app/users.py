"""User accounts + password-reset OTP — backed by the relational app DB
(``users`` + ``password_resets`` tables).

The tenant identity threaded everywhere is the user's surrogate uuid
(``User.id``), set as the session-cookie ``sub`` at login. Usernames/emails are
canonicalised to lowercase and unique. Password reset uses a hashed, expiring,
single-use email OTP (emailed via SMTP when configured; logged in dev).
"""

from __future__ import annotations

import asyncio
import logging
import re
import secrets
import smtplib
import uuid
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any

import bcrypt
from sqlalchemy import delete, select

from .db import db_session
from .db.models import PasswordReset, User, UserConfig

logger = logging.getLogger("joyjoy.users")

# Deterministic identity for the no-auth dev fallback (seeded by ensure_dev_user).
DEV_USERNAME = "dev-user"
DEV_USER_ID = uuid.uuid5(uuid.NAMESPACE_URL, "joyjoy:dev-user").hex

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


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_naive_utc(dt: datetime) -> datetime:
    """SQLite returns naive datetimes; Postgres returns aware. Coerce to naive UTC
    so comparisons never raise on a mixed offset."""
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _user_dict(u: User) -> dict:
    return {"id": u.id, "username": u.username, "email": u.email}


# ── User CRUD ──────────────────────────────────────────────────────────────
async def get_user(username: str) -> dict | None:
    """Look up by username (canonicalised). Backs the signup availability check."""
    async with db_session() as s:
        u = await s.scalar(select(User).where(User.username == _nu(username)))
        return _user_dict(u) if u else None


async def get_user_by_id(uid: str) -> dict | None:
    async with db_session() as s:
        u = await s.get(User, str(uid or ""))
        return _user_dict(u) if u else None


async def username_taken(username: str) -> bool:
    async with db_session() as s:
        return (await s.scalar(select(User.id).where(User.username == _nu(username)))) is not None


async def email_taken(email: str) -> bool:
    async with db_session() as s:
        return (await s.scalar(select(User.id).where(User.email == _ne(email)))) is not None


async def create_user(username: str, email: str, password: str) -> dict:
    """Create an account (+ its 1:1 UserConfig). Returns {ok, user} or
    {ok:False, error, field?}."""
    if not valid_username(username):
        return {"ok": False, "error": "Username must be 3–32 characters (letters, numbers, . _ -).", "field": "username"}
    if not valid_email(email):
        return {"ok": False, "error": "Enter a valid email address.", "field": "email"}
    if not valid_password(password):
        return {"ok": False, "error": "Password must be at least 8 characters.", "field": "password"}
    uid_name, em = _nu(username), _ne(email)
    async with db_session() as s:
        if await s.scalar(select(User.id).where(User.username == uid_name)):
            return {"ok": False, "error": "That username is already taken.", "field": "username"}
        if await s.scalar(select(User.id).where(User.email == em)):
            return {"ok": False, "error": "An account with that email already exists.", "field": "email"}
        u = User(username=uid_name, email=em, password_hash=hash_pw(password))
        s.add(u)
        await s.flush()  # populate u.id
        s.add(UserConfig(user_id=u.id, display_name=username.strip()))
        user = _user_dict(u)
    return {"ok": True, "user": user}


async def verify_credentials(username: str, password: str) -> dict | None:
    async with db_session() as s:
        u = await s.scalar(select(User).where(User.username == _nu(username)))
        if not u or not verify_pw(password, u.password_hash):
            return None
        return _user_dict(u)


async def set_password(user_id: str, new_password: str) -> bool:
    async with db_session() as s:
        u = await s.get(User, str(user_id or ""))
        if not u:
            return False
        u.password_hash = hash_pw(new_password)
        return True


async def change_password(user_id: str, current: str, new: str) -> dict:
    if not valid_password(new):
        return {"ok": False, "error": "New password must be at least 8 characters."}
    async with db_session() as s:
        u = await s.get(User, str(user_id or ""))
        if not u or not verify_pw(current, u.password_hash):
            return {"ok": False, "error": "Current password is incorrect."}
        u.password_hash = hash_pw(new)
    return {"ok": True}


# ── Password-reset OTP ───────────────────────────────────────────────────────
async def create_reset_otp(settings, email: str) -> tuple[str, str] | None:
    """Generate + store a hashed, expiring OTP (one active per user). Returns
    (otp, user_id) if the email is registered, else None (caller stays silent)."""
    em = _ne(email)
    async with db_session() as s:
        u = await s.scalar(select(User).where(User.email == em))
        if not u:
            return None
        otp = f"{secrets.randbelow(1_000_000):06d}"
        await s.execute(delete(PasswordReset).where(PasswordReset.user_id == u.id))
        s.add(
            PasswordReset(
                user_id=u.id, otp_hash=hash_pw(otp),
                expires_at=_now() + timedelta(minutes=settings.otp_ttl_minutes), attempts=0,
            )
        )
        return otp, u.id


async def verify_and_consume_otp(email: str, otp: str) -> dict:
    em = _ne(email)
    async with db_session() as s:
        u = await s.scalar(select(User).where(User.email == em))
        if not u:
            return {"ok": False, "error": "No reset code requested — request a new one."}
        pr = await s.scalar(
            select(PasswordReset)
            .where(PasswordReset.user_id == u.id)
            .order_by(PasswordReset.created_at.desc())
        )
        if not pr:
            return {"ok": False, "error": "No reset code requested — request a new one."}
        if datetime.utcnow() > _as_naive_utc(pr.expires_at):
            await s.execute(delete(PasswordReset).where(PasswordReset.user_id == u.id))
            return {"ok": False, "error": "Reset code expired — request a new one."}
        if pr.attempts >= _OTP_MAX_ATTEMPTS:
            await s.execute(delete(PasswordReset).where(PasswordReset.user_id == u.id))
            return {"ok": False, "error": "Too many attempts — request a new code."}
        if not verify_pw(str(otp or ""), pr.otp_hash):
            pr.attempts += 1
            return {"ok": False, "error": "Incorrect code."}
        await s.execute(delete(PasswordReset).where(PasswordReset.user_id == u.id))
        return {"ok": True, "user_id": u.id}


# ── Dev fallback user (no-auth dev mode tenancy bucket) ──────────────────────
async def ensure_dev_user(settings) -> None:
    """In dev, make sure the deterministic dev user (+ its config) exists so the
    no-auth fallback identity satisfies every per-user FK. No-op in prod."""
    if settings.is_prod:
        return
    async with db_session() as s:
        if not await s.get(User, DEV_USER_ID):
            s.add(
                User(
                    id=DEV_USER_ID, username=DEV_USERNAME, email="dev@dev.local",
                    password_hash=hash_pw(secrets.token_urlsafe(24)),
                )
            )
        if not await s.get(UserConfig, DEV_USER_ID):
            s.add(UserConfig(user_id=DEV_USER_ID, display_name="Dev User"))


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
