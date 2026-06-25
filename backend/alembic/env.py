"""Alembic environment — migrations for the joyjoy app DB.

Schema lives in ``app/db/models.py`` (``Base.metadata``). Alembic uses a SYNC
driver: the dev async ``sqlite+aiosqlite`` URL is rewritten to ``sqlite``, and the
prod ``postgresql+psycopg`` URL is sync-capable as-is. Set ``ALEMBIC_URL`` to
override (e.g. to generate the baseline against an empty database).

Note: fresh DBs are bootstrapped by ``create_all`` at app startup, so for an
already-created DB run ``alembic stamp head`` once; thereafter use
``revision --autogenerate`` + ``upgrade head`` for schema changes.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings
from app.db.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _sync_url() -> str:
    url = os.environ.get("ALEMBIC_URL")
    if url:
        return url
    return get_settings().app_db_url.replace("sqlite+aiosqlite://", "sqlite://")


def run_migrations_offline() -> None:
    context.configure(
        url=_sync_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {}) or {}
    section["sqlalchemy.url"] = _sync_url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
