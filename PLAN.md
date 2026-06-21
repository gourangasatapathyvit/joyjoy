# joyjoy — Multi-Tenant Deep Agents (React SPA + relational DB)

A **single FastAPI process** serving **many users** on one Deep Agents engine. It
serves both the **React SPA** and the `/v1` API, with **all application data in one
relational database** — **SQLite** (dev) or **Postgres** (prod), selected by
`APP_ENV`. Chat *messages* stay in LangGraph's checkpointer.

> This file is the living plan + checklist. Update the checkboxes as we go.

## 1. Goal & hard constraints
- **Single process, many users** — no per-user subprocess; `asyncio` concurrency.
- **All app data relational, prod in Postgres** so a pod can die with zero data loss:
  accounts, skins, providers, models, MCP servers, skills (+ files), sessions,
  per-user config + memory. Chat threads/checkpoints stay in the LangGraph saver.
- **Dev/prod parity** — dev = SQLite (`data/joyjoy.db`), prod = Postgres. *Same code*;
  the SQLAlchemy URL is derived from `APP_ENV` (`Settings.app_db_url`).
- **No file-based CRUD stores** — the old `models.json` / `mcp.json` / `ui.json` /
  KV-store layout is gone; everything is read/written through the DB.
- **Secrets at rest** — model `api_key`/AWS secrets are **Fernet-encrypted**
  (`CREDENTIAL_ENCRYPTION_KEY`, generate-once). Passwords are bcrypt. MCP secrets
  stay as `${VAR}` refs (real value in `.env`, never in the DB).
- **First-class React UI** — the SPA is the product; it's built and served by the backend.

## 2. Architecture
```
Browser
  │  same-origin fetch /v1/*  (httpOnly session cookie set on sign-in)
  ▼
joyjoy backend  (FastAPI, ONE process)   backend/app/
  • app.frontend()  → serves the built React SPA (frontend/dist) at /
  • auth.py        session cookie (sub = User.id) / JWT / dev fallback
  • users.py       accounts + password-reset OTP (users / password_resets)
  • agent.py       create_deep_agent() cached per (kind,user,model,reasoning);
  │                multi-provider build_model_for(); model/MCP/skills CRUD (async, DB)
  • dbfs.py        DB→agent bridge: MemoryBackend (/memory/) + UserSkillsBackend
  │                (/skills/user/) mounted in the agent's CompositeBackend
  • db/            13 SQLAlchemy models, async engine, Fernet crypto, seeds
  • persistence.py LangGraph saver+store (dev SQLite / prod Postgres)
  • runs.py        /v1/runs + SSE events + HITL approvals
  ▼
Model providers (build_model_for): Azure OpenAI · Azure AI Foundry/Claude · Bedrock · OpenAI-compat · Gemini
  ▼
Databases:  app DB (SQLite dev / Postgres prod)  +  LangGraph checkpointer/store (same engine)
```

## 3. Data model — the relational schema (`app/db/models.py`, 13 tables)
| Concern | Tables |
|---|---|
| Accounts / reset | `users` (uuid PK, bcrypt), `password_resets` |
| Shipped catalogs (seeded, read-only) | `skins`, `global_providers`, `global_models`, `global_skills`, `global_mcps` |
| Per-user | `user_configs` (1:1 — skin/theme/locale/activity/auto-follow/default model+reasoning/**memory: notes·about·persona**), `user_models`, `user_skills`, `user_mcps`, `skill_files` |
| Conversations | `sessions` (thread_id PK, relative `workspace_path`) |

Chat **messages** are NOT here — they live in the LangGraph checkpointer (Postgres
prod / SQLite dev). Provider secrets live Fernet-encrypted inside the model rows'
`settings` JSON. Migrations: Alembic (`backend/alembic/`); fresh DBs are bootstrapped
by `create_all` at startup, then `alembic stamp head` once for an existing DB.

## 4. Multi-tenant isolation
- Identity = **`User.id` (uuid)**, carried in the session-cookie `sub`. `resolve_user_id`
  returns it; dev no-auth falls back to a seeded deterministic dev user.
- Per-user tables FK → `users.id` (ON DELETE CASCADE). The agent's `/memory/` and
  `/skills/user/` mounts (via `dbfs.py`) and the workspace dir are all scoped by it.
- Global (shipped) skills/MCP/models are read-only; writes only ever touch the user's rows.

## 5. Repo layout
```
joyjoy/
  backend/
    app/{config,persistence,context,auth,users,agent,dbfs,sessions,usersettings,runs,workspace,media,main}.py
    app/db/{models,engine,crypto,seed,__init__}.py
    alembic/                relational migrations (baseline = all 13 tables)
    pyproject.toml
  frontend/                 React SPA (Vite + TS); built to frontend/dist, served by the backend
  skills/global/            read-only global skills (SKILL.md dirs) — seeded into the DB
  config/global.mcp.json    global MCP servers — seeded into the DB
  data/                     dev SQLite DBs + per-user workspace files (gitignored)
  docs/  PLAN.md  README.md  CLAUDE.md  .env
```

## 6. API surface (all `/v1`, user-scoped; global ids read-only)
- `GET /v1/health`, `GET /v1/models`
- Auth: `POST /v1/auth/{signup,login,logout,forgot,reset,change-password}`, `GET /v1/auth/{me,available}`
- `POST /v1/runs` + `GET /v1/runs/{id}/events` (SSE) + `/approvals/{aid}/respond` + `/cancel`
- Config/CRUD: `/v1/skills/*`, `/v1/skills/content`, `/v1/mcp/servers/*`, `/v1/mcp/tools`, `/v1/models/config*`, `/v1/memory*`, `/v1/settings/ui`, `/v1/skins`
- Sessions: `/v1/sessions*` (list/create/rename/delete/import/messages) · Workspace: `/v1/workspace/*`

## 7. Status / checklist
> Current architecture for contributors is in **[CLAUDE.md](./CLAUDE.md)**; run modes in **[docs/RUNNING.md](./docs/RUNNING.md)**.

- [x] **Scaffold** — persistence factory, agent factory, health, chat SSE, dev SQLite.
- [x] **Runs API + HITL** — `/v1/runs` + SSE + approvals; every MCP/plugin tool gated in run mode.
- [x] **Skills + MCP** — global (read-only) + per-user, runtime-loaded; full CRUD from the UI; 73 global skills; active MCP: jira (http), web-search (uvx duckduckgo), demo.
- [x] **Models / providers** — DB catalog, 5 provider types via `build_model_for`; Settings → Providers CRUD; keys masked.
- [x] **React SPA** — Vite + React 19 + TS (assistant-ui, Tailwind v4, shadcn, TanStack Query, i18n 16 langs, media rendering). **Single FastAPI server** via `app.frontend()`. Real auth (signup/login/forgot-OTP). **Legacy hermes-webui removed.**
- [x] **Relational-DB refactor** — all app data → SQLAlchemy (dev SQLite / prod Postgres via `APP_ENV`); Fernet secrets-at-rest; identity = `User.id`; memory → `UserConfig`; DB→agent bridge `dbfs.py`; frontend prefs → `/v1/settings/ui`; Alembic baseline. **Validated live (HTTP + browser).**
- [x] **Credentials** — provider secrets Fernet-encrypted at rest in the DB (no plaintext files).
- [~] **Prod Postgres** — store+saver + app DB on isolated `joyjoy_db` proven; load test + sandboxed `execute` still pending.
- [ ] **Ops** — docker-compose (backend + postgres), CI; pin provider SDKs (`langchain-anthropic`/`-aws`/`-google-genai`) into `pyproject.toml`.

## 7b. Runs queue & streaming — current design + agreed prod hardening
**Current (single-process — correct for now):** `backend/app/runs.py` uses one in-process
`asyncio.Queue` per run (producer = a `_drive` task; consumer = the `/v1/runs/{id}/events`
SSE generator), an in-memory `_RUNS` registry, and `asyncio.Future`s for HITL approvals —
the standard single-process SSE pattern (mirrors the sibling `ai_sdlc_dashboard`).

**Known weak spots (fine for dev/single-host):** the queue is unbounded (no backpressure);
`_RUNS` is in-memory (runs/approvals lost on restart).

**Agreed prod-hardening path (NOT a task broker, NOT multi-replica):** bound the queue
(`maxsize`, drop-oldest); durable run state in Redis (records + paused snapshots w/ TTL)
for restart-resume, durable agent state already in Postgres; stay single-pod (`Recreate`).
Heavier options only if needed: LangGraph Platform `langgraph-api`, or Redis Streams/NATS + arq/taskiq.

## 8. Dev run
```bash
bash ~/joyjoy/scripts/serve.sh           # build SPA + serve everything on :8080
# or:
cd ~/joyjoy/backend && uv venv && uv pip install -e .
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8080   # APP_ENV=dev → SQLite
curl -s 127.0.0.1:8080/v1/health
```
