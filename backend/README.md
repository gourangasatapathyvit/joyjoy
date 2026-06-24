# joyjoy backend

FastAPI + **deepagents/LangGraph** engine. A **single process** serves both the React SPA (`frontend/dist`, mounted via `app.frontend()`) and the `/v1` API to many users; **all application data lives in one relational DB** (dev SQLite / prod Postgres, by `APP_ENV`). One `create_deep_agent()` (cached per `(kind, user, model, reasoning)`) backs every chat; isolation is by `User.id` + `thread_id`.

For the system-wide picture see the repo root `ARCHITECTURE.md`; for run/setup see the root `README.md`; for contributor/agent notes see `CLAUDE.md`.

## Run & dev (uv-managed venv — no `pip`)

The app reads `../.env` (pydantic `env_file="../.env"`), so **run it from `backend/`**.

```bash
cd backend
uv sync                       # create/refresh .venv (dev extras: uv sync --extra dev)
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8080
curl -s 127.0.0.1:8080/v1/health
```

Usually you just run `scripts/restart_backend.sh` (restart) or `scripts/start_all.sh` (whole stack). ⚠️ **`uv sync` prunes anything not in `pyproject.toml`** — add deps there, never via `uv pip install` (an ad-hoc install gets wiped on the next sync). On first boot the app creates tables and loads `app/db/seeds/global_seed.sql` into an empty DB.

- **Lint/format:** `uv run ruff check app && uv run ruff format app` (dev extra).
- **Checks/tests:** no real pytest suite yet (deps are dev extras). `../scripts/validate_models.py` parses every model spec + resolves `${VAR}` keys. Validate behavior against the live `/v1` API with a real session cookie. **Never `import app.main` from a standalone script** — it opens a DB connection at import and hangs (parse `.env` into `os.environ` yourself).

## Layout (`app/`)

- `main.py` — app creation, lifespan/warm-up, `include_router` wiring, `app.frontend()` (SPA mounted last).
- `routes/` — the `/v1` API, split by concern: `auth chat runs sessions workspace mcp models skills memory settings_ui health` (+ `deps.py` shared deps).
- `agent.py` — **the core**: `_get_or_build()` compiles + caches the deep agent and invalidates the per-user cache on every write; async model/MCP/skill CRUD + `describe_*`; `build_backend()` chooses sandbox vs host filesystem; MCP load + per-run HITL gating. `agent_common.py` holds shared low-level bits (breaks import cycles).
- `dbfs.py` — DB→agent bridge: `MemoryBackend` (`/memory/`) + `DbSkillsBackend` (`/skills/{user,global}/`) deepagents backends (async DB, no disk). `memory_store.py`, `skills_store.py` support them.
- `db/` — `models.py` (13 tables), `engine.py` (async engine + `db_session()`), `crypto.py` (Fernet at rest), `seed.py` + `seeds/global_seed.sql` (single shipped seed). `alembic/` = prod migrations. **Adding a column:** SQLite `create_all` won't ALTER an existing table — dev: wipe `data/joyjoy.db*` or `ALTER TABLE`; prod: Alembic.
- `runs.py` — SSE runs engine (`/v1/runs` + events) with server-side HITL approval resolution (`Session.auto_approve`).
- `sandbox.py` / `sandbox_backend.py` / `workspace_sandbox.py` — OpenSandbox layer (gated by `SANDBOX_ENABLED`): lifecycle/dedicated-loop + per-workspace Docker volume / `BaseSandbox` bridge / dock FS facade. Talks to `opensandbox-server` on `:8090`.
- `workspace.py` / `media.py` — host filesystem dock + media resolver (used when sandbox off; `/v1/workspace/*` and `/v1/media` branch sandbox-vs-host).
- `config.py` (Settings), `persistence.py` (LangGraph saver+store), `auth.py`, `users.py` (accounts/OTP), `usersettings.py` (UI prefs ↔ `user_configs`), `sessions.py`, `context.py` (`AgentContext`), `prompts.py`, `constants.py`, `enums.py` (`Provider`/`McpStatus` StrEnums), `mcp_runtime.py` (MCP connection building), `textutils.py`.
- `mcp_servers/` — in-repo MCP servers run as subprocesses: `joyjoy_demo.py`, `workspace_fs/` (file delete/move/mkdir, per-session-scoped).

## Capabilities = global (read-only) + per-user (CRUD)

Skills, MCP servers, models, and memory share one shape, all in the DB: **global** rows (seeded from `global_seed.sql`, read-only) merged with **per-user** rows keyed by `User.id`. Writes to a global id are rejected; a user sees `global ∪ own`. CRUD lives in `agent.py` (`save_/delete_/toggle_user_*`); endpoints under `routes/`.

## Conventions & gotchas

- **Secrets** in `../.env` (gitignored): `JWT_SECRET`, `CREDENTIAL_ENCRYPTION_KEY` (generate-once), model keys, `OPENSANDBOX_API_KEY`, `SANDBOX_ENABLED`. Model/provider secrets are **Fernet-encrypted at rest**; the seed SQL holds only `${VAR}` env-refs; `describe_models` masks keys to the browser. MCP secrets are not stored — use `${VAR}` refs.
- **MCP stdio env:** the MCP SDK passes no inherited env, so `mcp_runtime`/`agent` inject PATH/HOME/cache + expand `${VAR}`. Avoid bare `npx` (can resolve to Windows npx and hang).
- After any model/MCP/skill/memory write the per-user agent cache is invalidated — route new writes through the `save_/delete_/toggle_` helpers so this holds.
