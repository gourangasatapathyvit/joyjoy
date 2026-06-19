"""joyjoy: optional multi-user account store for hermes-webui.

Backward-compatible: with no users defined, the single-password auth in
``api.auth`` keeps working unchanged. Once one or more users exist, the
(patched) login flow authenticates username+password against this store and
binds the session to the username via ``api.auth.create_session(username=...)``.
That username is then forwarded to the agent backend as ``X-User-Id`` for
per-user isolation.

Stored at ``STATE_DIR/users.json`` (mode 0600):
    {"users": {"alice": {"password_hash": "...", "created_at": 123.0}}}

Password hashing reuses ``api.auth._hash_password`` (PBKDF2-600k with the
per-install secret salt) so there is one hashing scheme for the whole app.
"""

from __future__ import annotations

import hmac
import json
import os
import re
import tempfile
import threading
import time

from api.auth import _hash_password
from api.config import STATE_DIR

_USERS_FILE = STATE_DIR / "users.json"
_LOCK = threading.Lock()
_USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")


def _load() -> dict:
    try:
        if _USERS_FILE.exists():
            data = json.loads(_USERS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("users"), dict):
                return data["users"]
    except Exception:
        pass
    return {}


def _save(users: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=STATE_DIR, suffix=".users.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"users": users}, f)
        os.chmod(tmp, 0o600)
        os.replace(tmp, _USERS_FILE)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def normalize(username: str) -> str:
    return (username or "").strip().lower()


def multi_user_enabled() -> bool:
    """True when at least one account exists (turns on username login)."""
    return bool(_load())


def list_users() -> list[str]:
    return sorted(_load().keys())


def add_user(username: str, password: str) -> None:
    username = normalize(username)
    if not _USERNAME_RE.match(username):
        raise ValueError("invalid username (a-z 0-9 . _ - ; must start alphanumeric)")
    if not password or len(password) < 6:
        raise ValueError("password must be at least 6 characters")
    with _LOCK:
        users = _load()
        users[username] = {"password_hash": _hash_password(password), "created_at": time.time()}
        _save(users)


def remove_user(username: str) -> bool:
    username = normalize(username)
    with _LOCK:
        users = _load()
        if username in users:
            users.pop(username)
            _save(users)
            return True
    return False


def verify_user(username: str, password: str) -> bool:
    username = normalize(username)
    rec = _load().get(username)
    if not rec:
        return False
    expected = rec.get("password_hash", "")
    return bool(expected) and hmac.compare_digest(_hash_password(password), expected)


# ── joyjoy: session ownership (per-user sidebar scoping) ─────────────────────
_SESSION_OWNERS_FILE = STATE_DIR / ".session_owners.json"
_OWNERS_LOCK = threading.Lock()


def _load_owners() -> dict:
    try:
        if _SESSION_OWNERS_FILE.exists():
            d = json.loads(_SESSION_OWNERS_FILE.read_text(encoding="utf-8"))
            if isinstance(d, dict):
                return {str(k): str(v) for k, v in d.items() if isinstance(v, str)}
    except Exception:
        pass
    return {}


def session_owners() -> dict:
    """Map of session_id -> owning username."""
    return _load_owners()


def set_session_owner(session_id, username: str) -> None:
    """Record the owning user for a session (idempotent, atomic write)."""
    sid = str(session_id or "")
    if not sid or not username:
        return
    with _OWNERS_LOCK:
        owners = _load_owners()
        if owners.get(sid) == username:
            return
        owners[sid] = username
        try:
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=STATE_DIR, suffix=".owners.tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(owners, f)
            os.chmod(tmp, 0o600)
            os.replace(tmp, _SESSION_OWNERS_FILE)
        except Exception:
            pass
