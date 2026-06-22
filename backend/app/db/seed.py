"""First-boot bootstrap: load the committed global (non-user) seed SQL into an
empty DB.

``app/db/seeds/global_seed.sql`` holds ALL shipped/global data — skins, providers,
base models, MCP servers, and the global skills + their files — as plain INSERTs.
It is the single source of global data; the DB is authoritative at runtime. This
runs once on first boot (when the DB is empty) and is a no-op afterwards.

Model API keys in the SQL are literal env-refs (``${AZURE_OPENAI_API_KEY}``) — NO
secret in the file; the real key lives in ``.env`` and is expanded at runtime by
``normalize_model``. Regenerate the SQL from a populated DB with
``scripts/dump_global_seed_sql.py``.
"""

from __future__ import annotations

import logging
import os

from sqlalchemy import select

from .engine import db_session, get_engine
from .models import Skin

logger = logging.getLogger("joyjoy.seed")

_SEED_SQL = os.path.join(os.path.dirname(__file__), "seeds", "global_seed.sql")


def _split_sql(sql: str) -> list[str]:
    """Split a SQL script into individual statements, respecting single-quoted
    string literals (with ``''`` escapes) and ``--`` line comments. Robust for our
    generated INSERTs, whose content may contain ``;``, ``--`` and newlines inside
    quoted literals. Drops BEGIN/COMMIT (we run inside one transaction)."""
    stmts: list[str] = []
    buf: list[str] = []
    i, n, in_str = 0, len(sql), False
    while i < n:
        ch = sql[i]
        if not in_str and ch == "-" and i + 1 < n and sql[i + 1] == "-":
            j = sql.find("\n", i)  # SQL line comment — skip to EOL
            i = n if j == -1 else j + 1
            continue
        if ch == "'":
            buf.append(ch)
            if in_str and i + 1 < n and sql[i + 1] == "'":
                buf.append("'")
                i += 2
                continue
            in_str = not in_str
            i += 1
            continue
        if ch == ";" and not in_str:
            stmt = "".join(buf).strip()
            if stmt:
                stmts.append(stmt)
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        stmts.append(tail)
    return [s for s in stmts if s.upper() not in ("BEGIN", "COMMIT")]


async def _already_seeded() -> bool:
    async with db_session() as s:
        return (await s.scalar(select(Skin.id).limit(1))) is not None


async def seed_all(settings) -> None:
    """Load global_seed.sql into the DB on first boot (when empty). No-op otherwise."""
    if await _already_seeded():
        return
    if not os.path.isfile(_SEED_SQL):
        logger.warning("No global seed SQL at %s — global data not seeded", _SEED_SQL)
        return
    with open(_SEED_SQL, encoding="utf-8") as f:
        statements = _split_sql(f.read())
    engine = get_engine()
    async with engine.begin() as conn:
        for stmt in statements:
            await conn.exec_driver_sql(stmt)
    logger.info("Loaded global seed: %d statements from %s", len(statements), os.path.basename(_SEED_SQL))
