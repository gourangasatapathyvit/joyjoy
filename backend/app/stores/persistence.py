"""Persistence factory — the single dev/prod swap point.

- **dev**  : SQLite saver + SQLite store (local files under ``data/``).
- **prod** : Postgres saver + Postgres store (everything in Postgres; pods stateless).

The agent code is identical for both; only the (checkpointer, store) pair changes.
Both are async context managers, so we open them in the FastAPI lifespan and keep
the connection pools alive for the process.
"""

from __future__ import annotations

import contextlib
import logging
from pathlib import Path
from typing import AsyncIterator

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.store.postgres.aio import AsyncPostgresStore
from langgraph.store.sqlite.aio import AsyncSqliteStore
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.core.config import Settings
from app.core.constants import PG_KEEPALIVE_ARGS, PG_POOL_MAX_IDLE_S, PG_POOL_MAX_LIFETIME_S

logger = logging.getLogger("joyjoy.persistence")


@contextlib.asynccontextmanager
async def open_persistence(settings: Settings) -> AsyncIterator[tuple[object, object]]:
    """Yield ``(checkpointer, store)`` for the active environment."""
    async with contextlib.AsyncExitStack() as stack:
        if settings.is_prod:
            dsn = settings.pg_dsn
            logger.info("persistence=postgres db=%s host=%s", dsn.rsplit("/", 1)[-1].split("?")[0], settings.db_host)
            # A connection POOL (not from_conn_string's single connection) so many
            # users can hit Postgres concurrently without serializing/erroring.
            #
            # RESILIENCE (critical for a REMOTE DB behind a firewall/NAT): an idle
            # pooled connection can be silently killed mid-flight by a stateful
            # firewall/NAT idle-timeout. Without guards, psycopg hands out the dead
            # connection, the next query black-holes on the dead socket, and the
            # kernel retransmits for ~13 min (tcp_retries2) before erroring — every
            # checkpoint write (which runs BEFORE the model call) then appears to hang.
            #   * check=check_connection → validate each connection on checkout, drop
            #     and replace dead ones instead of handing them out.
            #   * max_idle / max_lifetime → recycle connections before the firewall
            #     reaps them.
            #   * TCP keepalives + tcp_user_timeout (PG_KEEPALIVE_ARGS, passed as
            #     connect kwargs) → the OS detects a dead peer in ~1 min and a stuck
            #     send fails in ~15s, not 13 min.
            pool = AsyncConnectionPool(
                conninfo=dsn,
                max_size=int(settings.pg_pool_max),
                open=False,
                check=AsyncConnectionPool.check_connection,
                max_idle=PG_POOL_MAX_IDLE_S,
                max_lifetime=PG_POOL_MAX_LIFETIME_S,
                kwargs={
                    "autocommit": True,
                    "prepare_threshold": 0,
                    "row_factory": dict_row,
                    **PG_KEEPALIVE_ARGS,
                },
            )
            await pool.open()
            stack.push_async_callback(pool.close)
            checkpointer = AsyncPostgresSaver(pool)
            store = AsyncPostgresStore(pool)
        else:
            cp_path = Path(settings.sqlite_checkpoint_path)
            cp_path.parent.mkdir(parents=True, exist_ok=True)
            store_path = cp_path.with_name("dev_store.sqlite")
            logger.info("persistence=sqlite checkpoints=%s store=%s", cp_path, store_path)
            checkpointer = await stack.enter_async_context(AsyncSqliteSaver.from_conn_string(str(cp_path)))
            store = await stack.enter_async_context(AsyncSqliteStore.from_conn_string(str(store_path)))

        # Create tables / indexes (idempotent in langgraph).
        for component in (checkpointer, store):
            setup = getattr(component, "setup", None)
            if callable(setup):
                await setup()

        yield checkpointer, store
