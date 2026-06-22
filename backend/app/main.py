"""FastAPI app: assembly + lifespan only.

The HTTP handlers live in ``app/routes/*`` (one ``APIRouter`` per concern,
mounted below). This module owns app creation, the startup/shutdown lifespan
(env load, DB init/seed, persistence open, agent warm-up), CORS, the brand
static assets / favicons, and serving the built React SPA.

Single process, many users: one compiled agent per (user, model) is cached;
each request carries its own user_id + thread_id for isolation.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import users as users_mod
from .agent import get_agent
from .config import get_settings
from .db import ensure_encryption_key, init_db, seed_all
from .persistence import open_persistence
from .routes import (
    auth,
    chat,
    health,
    mcp,
    memory,
    models,
    runs,
    sessions,
    settings_ui,
    skills,
    workspace,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("joyjoy")
settings = get_settings()


def _load_env_file_into_environ() -> None:
    """Load ``.env`` KEY=VALUE pairs into os.environ (without overriding existing vars).

    Lets MCP server configs reference secrets via ``${VAR}`` (e.g. an API key) so the
    key stays out of the committed MCP config. pydantic loads .env into Settings but
    not into os.environ — this fills that gap for MCP subprocess ``env`` expansion.
    """
    for envfile in (".env", "../.env"):
        try:
            if not os.path.isfile(envfile):
                continue
            with open(envfile, encoding="utf-8") as f:
                for raw in f:
                    line = raw.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, val = line.partition("=")
                    key, val = key.strip(), val.strip()
                    if val[:1] not in ('"', "'", "{", "["):  # strip inline comment on simple values
                        val = val.split("  #", 1)[0].split(" #", 1)[0].strip()
                    if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
                        val = val[1:-1]
                    if key and key not in os.environ:
                        os.environ[key] = val
        except Exception:
            logger.debug("env load from %s failed", envfile, exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _load_env_file_into_environ()
    # App relational DB: resolve the encryption key (generate+persist on first
    # run), create tables, seed the global catalogs. Dev → SQLite, prod → Postgres.
    ensure_encryption_key(settings)
    await init_db()
    await seed_all(settings)
    await users_mod.ensure_dev_user(settings)  # dev no-auth tenancy bucket
    async with open_persistence(settings) as (checkpointer, store):
        app.state.checkpointer = checkpointer
        app.state.store = store
        await get_agent(settings, checkpointer, store, settings.default_model, "default")  # warm default
        logger.info(
            "joyjoy backend ready (env=%s, prod=%s, models=%s)",
            settings.app_env, settings.is_prod, list(settings.model_specs),
        )
        yield


app = FastAPI(title="joyjoy backend", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# joyjoy branding: serve the favicon + brand assets for anyone hitting the API in a browser
# (e.g. /docs). Files live in backend/static (copied from the joyjoy brand kit).
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")


@app.get("/favicon.ico", include_in_schema=False)
async def _favicon_ico():
    return FileResponse(os.path.join(_STATIC_DIR, "favicon.ico"), media_type="image/x-icon")


@app.get("/favicon.svg", include_in_schema=False)
async def _favicon_svg():
    return FileResponse(os.path.join(_STATIC_DIR, "favicon.svg"), media_type="image/svg+xml")


if os.path.isdir(_STATIC_DIR):
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

# Mount the concern routers (handlers live in app/routes/*).
for _mod in (
    health, auth, models, mcp, skills, memory, workspace, settings_ui, chat, runs, sessions
):
    app.include_router(_mod.router)


# ── Serve the built React SPA (single-server / Phase 4) ──────────────────────
# FastAPI 0.138+'s `app.frontend()` serves the Vite `dist` as LOW-PRIORITY routes:
# the /v1 API, /static and favicons are matched first, and the frontend (hashed
# assets + index.html) only if nothing else matched. `fallback="auto"` returns
# index.html for unmatched client routes so /settings, /signin, … resolve on
# direct navigation / refresh. Gated on the build existing so dev (no dist) is fine.
_FRONTEND_DIST = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")
)
if os.path.isfile(os.path.join(_FRONTEND_DIST, "index.html")):
    app.frontend("/", directory=_FRONTEND_DIST, fallback="auto")
    logger.info("serving SPA from %s", _FRONTEND_DIST)
