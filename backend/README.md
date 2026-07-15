# joyjoy backend

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/branding/svg/joyjoy-dark.svg">
    <img src="../docs/branding/png/joyjoy-primary.png" alt="joyjoy" width="280">
  </picture>
</p>

Multi-tenant **Deep Agents** backend: a single **FastAPI** process that serves the React SPA and the `/v1` JSON/SSE API on one port (`:8080`). One compiled agent per `(run/chat, user, model, reasoning, genui)` is cached in-process; every request carries its own `user_id` + `thread_id` for tenant isolation.

> Big-picture architecture (data flow, security tiers, deployment) lives in [`../ARCHITECTURE.md`](../ARCHITECTURE.md). This README is the backend dev guide.

## Stack

- **Python ≥ 3.11**, FastAPI + uvicorn, SSE via `sse-starlette`
- **Agent engine**: `deepagents` 0.6.11 on `langgraph` ≥1.2 (`langchain-core`, `langchain-mcp-adapters`)
- **Model providers**: Azure OpenAI, Anthropic (incl. Azure AI Foundry `/anthropic`), AWS Bedrock, Google GenAI
- **Persistence**: SQLAlchemy 2.0 (async) app DB + LangGraph checkpointer — SQLite (dev) / Postgres (prod, `psycopg`); Alembic migrations
- **Secrets at rest**: Fernet (`cryptography`); accounts via `bcrypt` + signed session cookie / JWT

## Layout (`app/`)

```
main.py        # app assembly + lifespan (env load, DB init/seed, persistence, agent warm-up, SPA mount)
core/          # config.py (Settings), auth.py, context.py, constants, enums, text/time utils
db/            # models.py (schema), engine.py, crypto.py (Fernet), seed.py, seeds/*.sql
agent/         # agent.py (build + per-key cache), prompts.py, middleware.py, runs.py (SSE + HITL), agent_common.py
routes/        # one APIRouter per concern (see API surface below)
stores/        # sessions, users, usersettings, skills_store, mcp_runtime, memory_store,
               #   persistence (checkpointer/store), dbfs (DB→agent-FS bridge)
workspace/     # workspace.py (per-thread files), media.py (/v1/media; office→PDF via LibreOffice)
sandbox/       # OpenSandbox integration (opt-in code/shell execution)
mcp_servers/   # bundled MCP servers (joyjoy_demo.py, workspace_fs)
```

## Run (dev)

```bash
cd backend
uv pip install -e .            # installs deps into the active interpreter
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
# or: ../scripts/run-backend.sh
```

Dev defaults (`DEV_MODE=true` + `COMPOSE_PROFILES=devdb`): SQLite app DB (`./data/joyjoy.db`) + SQLite checkpointer + a no-auth dev user resolved from the `X-User-Id` header. On first boot the global catalogs (skins/providers/models/skills/MCP) are seeded from `app/db/seeds/global_seed.sql`.

Full stack (backend + SPA + jira MCP, WSL): `../scripts/start_all.sh`. Containerized: see [`../ARCHITECTURE.md`](../ARCHITECTURE.md) §6 (`docker compose up --build`).

## Configuration

Settings come from env / `.env` (pydantic-settings; field names map case-insensitively to `UPPER_SNAKE`). Common ones:

| Var | Purpose |
|-----|---------|
| `DEV_MODE` | `true` = dev-relaxed auth (no-auth `X-User-Id` header + auto dev user); `false` = strict cookie/JWT auth |
| `COMPOSE_PROFILES` | the single infra switch: `localdb`/`devdb`/`server` (db backend) + `sandbox` + `observability`. The backend self-derives its DB mode, sandbox, and metrics/tracing from this |
| `DB_HOST` / `DB_PORT` / `DB_USERNAME` / `DB_PASSWORD` | Postgres server (used when db mode is `localdb` or `server`; blank in `localdb` = bundled-container defaults) |
| `APP_DB_NAME` / `LANGGRAPH_CHECKPOINT_DB` | the two **separate** Postgres databases: app data vs LangGraph checkpoints |
| `JWT_SECRET` | signs session cookies / per-user JWTs — **required & stable when `DEV_MODE=false`** |
| `CREDENTIAL_ENCRYPTION_KEY` | Fernet key for secrets at rest — **generate once; rotating it orphans stored secrets** |
| `AZURE_OPENAI_API_KEY` / `AZURE_OPENAI_ENDPOINT` | base model creds (seeded models reference `${AZURE_OPENAI_API_KEY}`) |
| `WORKSPACE_ROOT` | agent workspace files root (`/data` volume in the baked stack) |
| `JOYJOY_INTERRUPT_TOOLS` | extra built-in tools to gate for HITL approval (MCP/plugin tools auto-gate) |
| `OPENSANDBOX_API_KEY` / `SANDBOX_*` | code-execution sandbox connection details (the `sandbox` profile is the on/off switch) |
| `OTEL_EXPORTER_OTLP_*` / `LANGFUSE_*` | metrics/tracing transport details (the `observability` profile is the on/off switch) |

Model & MCP secrets are referenced as `${VAR}` in the DB/config and expanded at agent build, so keys stay out of the committed seed. `describe_mcp` returns the original `${VAR}` refs — never the expanded secret.

## API surface (`/v1`, mounted in `main.py`)

`health` · `auth` (signup/login/OTP/me) · `models` (+providers, incl. `/v1/models/config/discover` — fetch a provider's live catalog — and `/save-bulk` — save several discovered models at once) · `mcp` (servers/tools CRUD) · `skills` (global read-only + user CRUD) · `memory` (AGENTS.md + notes) · `workspace` (file CRUD + `/v1/media`) · `settings_ui` (UI prefs) · `chat` · `runs` (SSE run loop + approvals + `/v1/capabilities`) · `sessions` (per-user sidebar).

Chat runs stream tokens, tool calls, and HITL approval interrupts over SSE; everything else is plain JSON.

## Key concepts

- **Agent cache** (`agent.py:_get_or_build`): key `("run"|"chat", uid, model, effort, genui)`. Tools = per-user MCP tools (cached, workspace-bound) + generative-UI tools `render_ui`/`render_html` (when `genui`) + `load_skill` (sandbox only). These render-tools are **native in-process `StructuredTool`s, not MCP** — the spec/HTML rides in the tool-call args and the frontend renders it.
- **HITL**: in run mode, `interrupt_on` gates all MCP/plugin tools (+ `JOYJOY_INTERRUPT_TOOLS` + sandbox `execute`); per-thread `auto_approve` can bypass.
- **DB→agent FS bridge** (`stores/dbfs.py`): serves `/memory/AGENTS.md` and `/skills/*` from the DB into the agent's virtual filesystem.
- **Middleware** (`agent/middleware.py`): `StripStaleThinkingMiddleware` (fixes multi-turn thinking-block replays) + production guards (call/tool limits, transient retry, context trimming), additive over deepagents' built-ins.
- **Messages live in the LangGraph checkpointer**, not the relational DB. The relational DB holds accounts, catalogs, per-user skills/MCP/models, and `sessions` metadata.
- **Observability** (`app/core/observability.py`, both opt-in): tracing is pure env-var (LangChain → OTLP → self-hosted Langfuse via LangSmith's OTEL bridge); metrics are a Prometheus registry at `/metrics` fed by an ASGI middleware + a per-run `PrometheusCallbackHandler` + `record_*` calls in the run loop. Backing stack = the `observability` compose profile. See ARCHITECTURE.md §7a.
- **Model discovery** (`agent.py`: `discover_models`, `save_user_models_bulk`, `_composite_model_id`): the Providers tab can fetch a provider's live model catalog instead of hand-typing an id (per-provider adapters for Azure OpenAI, Anthropic, Bedrock, OpenAI-compatible endpoints, and Gemini), then bulk-save a selection. Per-user model ids are `{provider}:{raw_id}` composites so the same base name can exist under multiple providers without colliding with a global (bare-id) model.

## Testing & migrations

```bash
uv pip install -e '.[dev]'
pytest                # tests/ (asyncio mode)
ruff check app        # lint
alembic upgrade head  # DB migrations
```
