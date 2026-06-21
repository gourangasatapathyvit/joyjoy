"""Secrets-at-rest. Every secret field (API keys, AWS secret/session tokens)
stored inside a model/MCP ``settings`` JSON blob is Fernet-encrypted before it
touches the DB and decrypted only when the agent actually builds a chat model.

The key lives in ``CREDENTIAL_ENCRYPTION_KEY`` (.env). It is generate-once: if
absent we mint one and persist it, because rotating it would orphan every
already-stored secret. Encrypted values carry an ``enc:`` prefix so plaintext
(legacy / hand-edited) values pass through untouched on decrypt.
"""

from __future__ import annotations

import logging
import os

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger("joyjoy.crypto")

# Secret keys that must never be persisted in the clear.
SECRET_FIELDS = ("api_key", "aws_secret_access_key", "aws_session_token")

_PREFIX = "enc:"
_fernet: Fernet | None = None


def _env_candidates() -> list[str]:
    return [".env", os.path.join("..", ".env")]


def _persist_key_to_env(key: str) -> None:
    """Write CREDENTIAL_ENCRYPTION_KEY=<key> into the first existing .env (or
    create ./.env). Replaces an existing (possibly empty) line in place."""
    target = next((p for p in _env_candidates() if os.path.isfile(p)), ".env")
    line = f"CREDENTIAL_ENCRYPTION_KEY={key}\n"
    try:
        existing = ""
        if os.path.isfile(target):
            with open(target, encoding="utf-8") as f:
                existing = f.read()
        lines = existing.splitlines(keepends=True)
        replaced = False
        for i, ln in enumerate(lines):
            if ln.strip().startswith("CREDENTIAL_ENCRYPTION_KEY="):
                lines[i] = line
                replaced = True
                break
        if not replaced:
            if existing and not existing.endswith("\n"):
                lines.append("\n")
            lines.append(line)
        with open(target, "w", encoding="utf-8") as f:
            f.write("".join(lines))
        logger.info("Generated CREDENTIAL_ENCRYPTION_KEY and persisted to %s", target)
    except Exception:
        logger.warning("Could not persist CREDENTIAL_ENCRYPTION_KEY to %s", target, exc_info=True)


def ensure_encryption_key(settings) -> str:
    """Resolve the Fernet key (generate+persist on first run). Idempotent;
    call once at startup before any encrypt/decrypt."""
    global _fernet
    key = (settings.credential_encryption_key or os.environ.get("CREDENTIAL_ENCRYPTION_KEY") or "").strip()
    if not key:
        key = Fernet.generate_key().decode()
        _persist_key_to_env(key)
        os.environ["CREDENTIAL_ENCRYPTION_KEY"] = key
        # keep the in-memory Settings consistent for the rest of the process
        try:
            settings.credential_encryption_key = key
        except Exception:
            pass
    _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    return key


def _f() -> Fernet:
    if _fernet is None:
        raise RuntimeError("encryption key not initialised — call ensure_encryption_key() at startup")
    return _fernet


def encrypt(value: str) -> str:
    """Encrypt a plaintext secret -> ``enc:<token>``. Empty/already-encrypted
    values pass through unchanged."""
    if value is None:
        return ""
    s = str(value)
    if not s or s.startswith(_PREFIX):
        return s
    return _PREFIX + _f().encrypt(s.encode()).decode()


def decrypt(value: str) -> str:
    """Decrypt an ``enc:`` value back to plaintext. Non-prefixed values are
    returned as-is (legacy plaintext); an undecryptable token returns ""."""
    if not value:
        return ""
    s = str(value)
    if not s.startswith(_PREFIX):
        return s
    try:
        return _f().decrypt(s[len(_PREFIX):].encode()).decode()
    except InvalidToken:
        logger.warning("Could not decrypt a stored secret (wrong key?)")
        return ""


def encrypt_secrets(data: dict) -> dict:
    """Return a copy of ``data`` with every SECRET_FIELDS value encrypted."""
    out = dict(data or {})
    for k in SECRET_FIELDS:
        if out.get(k):
            out[k] = encrypt(out[k])
    return out


def decrypt_secrets(data: dict) -> dict:
    """Return a copy of ``data`` with every SECRET_FIELDS value decrypted."""
    out = dict(data or {})
    for k in SECRET_FIELDS:
        if out.get(k):
            out[k] = decrypt(out[k])
    return out
