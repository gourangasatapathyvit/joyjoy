"""Async SQLAlchemy engine for the app DB.

One engine per process, built lazily from ``settings.app_db_url`` (dev → a local
SQLite file via aiosqlite; prod → the shared Postgres via psycopg async). Use the
``db_session()`` async context manager for a unit of work; it commits on clean
exit and rolls back on error.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ..config import get_settings
from .models import Base

logger = logging.getLogger("joyjoy.db")

_engine = None
_sessionmaker: async_sessionmaker | None = None


def _ensure_sqlite_dir(url: str) -> None:
    """Make the parent dir for a sqlite file URL (``sqlite+aiosqlite:///abs/path``)."""
    marker = ":///"
    if "sqlite" in url and marker in url:
        path = url.split(marker, 1)[1]
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        url = settings.app_db_url
        kwargs: dict = {"echo": False, "future": True, "pool_pre_ping": True}
        if url.startswith("postgresql"):
            kwargs["pool_size"] = settings.pg_pool_max
            kwargs["max_overflow"] = 0
        else:
            _ensure_sqlite_dir(url)
        _engine = create_async_engine(url, **kwargs)
        if url.startswith("sqlite"):
            # SQLite ignores FK constraints unless asked per-connection — turn it
            # on so ON DELETE CASCADE actually fires in dev.
            @event.listens_for(_engine.sync_engine, "connect")
            def _enable_sqlite_fk(dbapi_conn, _rec):  # noqa: ANN001
                cur = dbapi_conn.cursor()
                cur.execute("PRAGMA foreign_keys=ON")
                cur.close()

        logger.info("App DB engine ready (%s)", url.split("://", 1)[0])
    return _engine


def get_sessionmaker() -> async_sessionmaker:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(get_engine(), expire_on_commit=False, class_=AsyncSession)
    return _sessionmaker


@asynccontextmanager
async def db_session():
    """Yield an ``AsyncSession``; commit on success, roll back on exception."""
    sm = get_sessionmaker()
    async with sm() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Create all tables if missing (idempotent). Alembic owns schema *changes*;
    this just bootstraps a fresh DB so dev needs no migration step."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("App DB schema ensured (%d tables)", len(Base.metadata.tables))


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
