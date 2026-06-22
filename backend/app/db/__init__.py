"""Relational app DB (dev SQLite / prod Postgres). See models.py for the schema."""

from __future__ import annotations

from . import models
from .crypto import (
    SECRET_FIELDS,
    decrypt,
    decrypt_secrets,
    encrypt,
    encrypt_secrets,
    ensure_encryption_key,
)
from .engine import db_session, dispose_engine, get_engine, get_sessionmaker, init_db
from .seed import seed_all


async def get_or_create_user_config(session, user_id: str) -> "models.UserConfig":
    """Fetch the user's ``UserConfig`` row, creating (+adding) it if absent.

    The get-or-create pattern was duplicated across usersettings/agent/dbfs;
    this is the single shared implementation."""
    uid = str(user_id or "")
    cfg = await session.get(models.UserConfig, uid)
    if cfg is None:
        cfg = models.UserConfig(user_id=uid)
        session.add(cfg)
    return cfg


__all__ = [
    "models",
    "db_session",
    "get_or_create_user_config",
    "get_engine",
    "get_sessionmaker",
    "init_db",
    "dispose_engine",
    "seed_all",
    "ensure_encryption_key",
    "encrypt",
    "decrypt",
    "encrypt_secrets",
    "decrypt_secrets",
    "SECRET_FIELDS",
]
