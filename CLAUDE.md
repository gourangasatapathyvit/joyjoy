# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

joyjoy is a multi-tenant **Deep Agents** platform: one **FastAPI** process serves the **React SPA** and the **`/v1` JSON/SSE API** on a single origin (`:8080`). See `ARCHITECTURE.md` for the full design; `backend/README.md` and `frontend/README.md` for per-package dev guides.

## Environment

The code lives and runs in **WSL** (`~/joyjoy`). Run all build/test/docker commands from inside WSL (`wsl -d Ubuntu bash -lc '...'`), not Windows PowerShell — the inline `VAR=value cmd` form and the toolchain (uv, docker) are Linux-side.

## Commands

Backend (`cd backend`):
```bash
uv pip install -e .                                   # deps (add '.[dev]' for pytest/ruff)
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload   # run (dev: SQLite + no-auth)
pytest                                                # all tests (asyncio mode, tests/)
pytest tests/test_prompts.py::test_name -q            # single test
ruff check app                                        # lint
alembic upgrade head                                  # DB migrations
```

Frontend (`cd frontend`):
```bash
npm install
npm run dev        # Vite :5173 (proxies /v1 → :8080, injects x-user-id: alice)
npm run build      # tsc -b && vite build → dist/
npm run check      # Biome lint + format (write)
```

Full stack / containers:
```bash
scripts/start_all.sh                                  # WSL dev: jira MCP → backend → SPA (idempotent)
docker compose up --build                             # single image (SPA baked in), :8080
COMPOSE_PROFILES=localdb,sandbox,observability docker compose up --build   # + bundled PG + sandbox + observability
docker compose -f docker-compose.dev.yml up -d        # infra ONLY (no backend); run backend on host
scripts/dev-up.sh                                     # picks baked vs infra-only from DEV_MODE in .env
```

## Architecture (the parts that span files)

- **Single process, many users.** `app/main.py` mounts one `APIRouter` per concern (`app/routes/*`) and serves the built SPA via `app.frontend()`. Tenant identity (`user_id`) + `thread_id` ride on every request; there is no per-user process.
- **Agent build + cache** (`app/agent/agent.py:_get_or_build`). Compiled deepagents graphs are cached by key `("run"|"chat", uid, model, effort, genui)`. Tools are baked at build time: per-user MCP tools (cached per user, workspace-bound) + generative-UI tools + `load_skill` (sandbox only). **Changing tool availability means changing the cache key** (e.g. `genui` gates the render tools). `_invalidate_user_cache(uid)` after any per-user skill/MCP/model/memory write.
- **Run loop + HITL** (`app/agent/runs.py`). `POST /v1/runs` streams tokens, tool calls, and approval interrupts over SSE. In run mode, `interrupt_on` gates **all** MCP/plugin tools (+ `JOYJOY_INTERRUPT_TOOLS` built-ins + sandbox `execute`); per-thread `auto_approve` bypasses.
- **Two persistence layers.** Chat **messages live only in the LangGraph checkpointer** (`app/stores/persistence.py` — SQLite dev / Postgres prod). The relational app DB (`app/db/models.py`, SQLAlchemy async) holds everything else: accounts, global catalogs, per-user skills/MCP/models, and `sessions` metadata. Don't look for messages in the relational DB.
- **DB→agent filesystem bridge** (`app/stores/dbfs.py`). The agent's `/memory/AGENTS.md` and `/skills/*` are served from the DB into its virtual FS — skills/memory are edited via DB CRUD, not loose files.
- **Frontend = external-store runtime** (`frontend/src/runtime/JoyjoyRuntimeProvider.tsx`). assistant-ui in external-store mode: the app owns chat state (zustand + a custom SSE client), not a built-in runtime. Tool calls render inline via the `TOOL_UIS` map (`components/assistant-ui/tool-uis.tsx`).
- **Generative UI.** `render_ui` (JSON kit → native `MessagePrimitive.GenerativeUI`) and `render_html` (sandboxed iframe canvas) are **native in-process `StructuredTool`s, not MCP** — server-side they're no-ops; the spec/HTML rides in the tool-call args and the frontend renders it (and it persists across reloads via those args). Gated per session by the `generative_ui` run flag.
- **Model discovery spans agent.py → routes/models.py → ProvidersPanel.tsx.** `discover_models`/`save_user_models_bulk` (`app/agent/agent.py`) let the Providers tab fetch a provider's live catalog (`POST /v1/models/config/discover`) and bulk-save a selection (`/save-bulk`), reused by both the Add dialog (multi-select) and the Edit dialog (pick-one to switch a model's deployment). Per-user model ids are `{provider}:{raw_id}` composites (`_composite_model_id`) so the same base name can exist under multiple providers without colliding with a global (bare-id) model — `save_user_model` edits an EXISTING row in place by exact id match before falling back to compositing a new one, so legacy bare ids don't get silently duplicated.

## Gotchas

- **Config is profile-driven.** `COMPOSE_PROFILES` is the single switch: it sets `Settings.db_mode` (`devdb` → SQLite; `localdb`/`server` → Postgres, with app data in `APP_DB_NAME` and LangGraph checkpoints in the *separate* `LANGGRAPH_CHECKPOINT_DB`) and auto-derives `sandbox_enabled`/`metrics_enabled`/`tracing_enabled` (from the `sandbox`/`observability` profiles). Separately, `DEV_MODE` toggles auth strictness — `true` → no-auth dev user (identity from `X-User-Id`); `false` → cookie/JWT auth (**the dev header is ignored**). `is_prod` is now just `not dev_mode`. `app/core/config.py` is the single source for settings.
- **Secrets are `${VAR}` refs.** Model/MCP configs in the DB/seed reference `${VAR}`, expanded at agent build from `os.environ` (`main.py` loads `.env` into `os.environ`). Keys never live in the seed; `describe_mcp` must never return the *expanded* secret. Encrypted secrets in the DB use Fernet (`CREDENTIAL_ENCRYPTION_KEY` — rotating it orphans them).
- **Prod serves the baked SPA.** The backend serves `frontend/dist` (copied into the image at build). Editing frontend source needs `vite build` + `docker compose up -d --build` to show up in the container; a hot-swapped `dist` is ephemeral.
- **Dev frontend identity.** Use `http://localhost:5173` (secure context — `crypto.randomUUID`; a raw WSL IP breaks the app). The Vite proxy injects `x-user-id: alice`, so seed a `User(id="alice")` or you stay on `/signin`.
- **MCP servers in WSL: avoid bare `npx`.** It resolves to Windows `npx` (CMD/UNC failures) — prefer `uvx`/Python MCP servers. `main.py` injects `${JOYJOY_PYTHON}`/`${JOYJOY_UVX}`/`${JOYJOY_BACKEND}` so DB MCP rows stay portable.
- **i18n is strictly typed.** Locale files are `Resources = typeof en`; a new key must be added to all 16 locales or types break.
- **`devdb` persistence in the baked stack depends on `CONTAINER_DATA_DIR`.** `docker-compose.yml`'s `backend` service derives `WORKSPACE_ROOT`/`APP_DB_PATH`/`SQLITE_CHECKPOINT_PATH` AND the `workspaces` volume mount target from the same `${CONTAINER_DATA_DIR:-/data}` — if you ever change one without the other, `devdb` mode's SQLite files land back on the container's ephemeral writable layer and get wiped on the next `docker compose up --build`.
