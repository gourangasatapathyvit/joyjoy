# Architecture Overview

This document gives a high-level, "bird's-eye" view of **joyjoy** so contributors and agents can navigate and contribute quickly. It deliberately avoids low-level detail (which goes stale) — for exact APIs read the code; for dev/run specifics see `README.md` and `CLAUDE.md`. Keep it updated as the architecture evolves.

**One-line summary:** a single FastAPI process serves a React SPA *and* a `/v1` API to many users; one shared Deep Agent (deepagents + LangGraph) backs every chat; all application data lives in one relational DB; agent code/file execution optionally runs in a per-`(user, thread)` OpenSandbox container.

## 1. Project Structure

```
joyjoy/
├── backend/                     # FastAPI + deepagents engine (also serves the SPA)
│   ├── app/
│   │   ├── main.py              # app creation, lifespan, router wiring, app.frontend(SPA)
│   │   ├── agent.py             # core: build/cache deep agents, model+MCP+skill CRUD (async)
│   │   ├── prompts.py           # system prompts (triple-quoted)  ·  constants.py (DEFAULT_USER_ID, caps)
│   │   ├── config.py            # pydantic Settings (APP_ENV-driven dev/prod)  ·  persistence.py (LG saver+store)
│   │   ├── auth.py users.py usersettings.py sessions.py   # identity, accounts/OTP, prefs, session registry
│   │   ├── context.py runs.py   # AgentContext  ·  SSE runs engine + HITL approvals
│   │   ├── dbfs.py              # DB→agent bridge: MemoryBackend + DbSkillsBackend (deepagents backends)
│   │   ├── sandbox.py sandbox_backend.py workspace_sandbox.py   # OpenSandbox lifecycle / backend / dock FS
│   │   ├── workspace.py media.py                                # host filesystem dock + media resolver
│   │   ├── routes/             # API split by concern: auth chat runs sessions workspace mcp models skills memory settings_ui health
│   │   └── db/                 # models.py (13 tables), engine.py, crypto.py (Fernet), seeds/global_seed.sql
│   ├── alembic/                # prod DB migrations
│   └── pyproject.toml          # uv-managed deps (no pip)
├── frontend/                    # React 19 + Vite SPA (built to frontend/dist, served by backend)
│   └── src/  (api/ runtime/ components/assistant-ui/ components/chat/ routes/ i18n/ store/ lib/)
├── sandbox-image/Dockerfile     # multi-language joyjoy/sandbox-fat:<N> execution image
├── scripts/                     # start_all.sh (full stack), serve.sh, restart_backend.sh, validate_models.py
├── data/                        # dev SQLite DBs + host workspaces (gitignored)
├── docs/                        # branding kit, RUNNING.md, etc.
├── sandbox.toml docker-compose.yml .env(.example)
└── README.md  CLAUDE.md  ARCHITECTURE.md  PLAN.md
```

## 2. High-Level System Diagram

```
                          ┌────────────────────────────────────────────┐
   Browser (SPA, same     │   FastAPI process  (:8080, single origin)   │
   origin, cookie auth)   │                                            │
        │  /v1/* + SSE     │   app.frontend()  →  serves frontend/dist   │
        └─────────────────▶   /v1 API  ──▶  one create_deep_agent()     │
                          │        (deepagents + LangGraph)             │
                          └───┬───────────┬────────────┬──────────┬─────┘
        relational app DB ◀───┘           │            │          │
   (SQLite dev / Postgres prod;           │            │          └─▶ Model provider APIs
    accounts, skills, mcp, models,        │            │             (Azure OpenAI, Anthropic/
    sessions, config, memory)             │            │              Foundry, Bedrock, OpenAI-
                                          │            │              compat, Gemini)
   LangGraph checkpointer + store ◀───────┘            │
   (chat messages; /memories cross-thread)             │
                                                       ▼
                            MCP servers (HTTP/stdio): jira :9000, web-search,
                            joyjoy-demo, workspace-fs  ─ tools gated for HITL approval
                                                       │
   OpenSandbox server :8090  (Docker) ◀───────────────┘  when SANDBOX_ENABLED:
        └─ per-(user,thread) container + durable Docker volume per workspace
           = where the agent's file CRUD + code/shell actually run
```

Key boundaries: the **browser is same-origin** (no separate UI server); **all app state is in the relational DB** (the only other persistence is LangGraph's checkpointer/store and, in sandbox mode, the per-workspace Docker volume); **MCP + sandbox are out-of-process**, reached over HTTP/stdio.

## 3. Core Components

### 3.1. Frontend
- **Name:** joyjoy SPA.
- **Description:** the entire UI — chat (assistant-ui), per-conversation workspace dock, and Settings/Skills/MCP/Memory tabs. Talks to `/v1/*` same-origin with `credentials:"include"`; chat streams via SSE (`/v1/runs/{id}/events`) and renders HITL tool-approval cards inline.
- **Technologies:** React 19, TypeScript, Vite, assistant-ui, Tailwind v4, shadcn, TanStack Query, react-i18next, Zustand.
- **Deployment:** built to `frontend/dist` and served by the backend — **no separate frontend server**.

### 3.2. Backend Services

#### 3.2.1. joyjoy backend (the single process)
- **Name:** FastAPI app (`backend/app`).
- **Description:** serves the SPA **and** the `/v1` API, runs the Deep Agent engine, owns all DB access, identity/auth, the runs/HITL engine, and the workspace dock. One `create_deep_agent()` is compiled+cached per `(kind, user_id, model, reasoning)`; per-user isolation is by `User.id` + `thread_id`.
- **Technologies:** Python 3.11+, FastAPI, deepagents (==0.6.11), LangGraph, SQLAlchemy (async), pydantic-settings, uvicorn, uv-managed venv.
- **Deployment:** one uvicorn process on `:8080` (dev script or `docker-compose`).

#### 3.2.2. OpenSandbox server (execution layer)
- **Name:** `opensandbox-server` (`:8090`, separate process via `uvx`).
- **Description:** control plane that provisions per-`(user, thread)` containers (Docker runtime) where the agent's file ops + code/shell run. The backend talks to it via the `opensandbox` SDK; durability is a Docker named volume per workspace. Gated by `SANDBOX_ENABLED` (off → host filesystem instead).
- **Technologies:** OpenSandbox (FastAPI control plane + in-container `execd`), Docker, the multi-language `joyjoy/sandbox-fat` image.

#### 3.2.3. MCP tool servers
- **Name:** jira (mcp-atlassian, `:9000`), web-search (DuckDuckGo via uvx), joyjoy-demo, workspace-fs.
- **Description:** out-of-process tool providers (HTTP or stdio) loaded per-user; every MCP tool is gated for HITL approval in the runs API.

## 4. Data Stores

### 4.1. Relational application DB
- **Type:** SQLite (dev, `data/joyjoy.db`) / PostgreSQL (prod) — selected by `APP_ENV`.
- **Purpose:** **all application data** — no file-based stores. Provider secrets are Fernet-encrypted at rest.
- **Key tables (13):** `users`, `password_resets`, `skins`, `global_providers`, `global_models`, `global_mcps`, `global_skills`, `user_configs`, `user_models`, `user_skills`, `user_mcps`, `skill_files`, `sessions`. The capability pattern = **global (shipped, read-only) merged with per-user (CRUD)**; global rows seed from `backend/app/db/seeds/global_seed.sql`.

### 4.2. LangGraph checkpointer + store
- **Type:** SQLite (`data/dev_checkpoints.sqlite`, `data/dev_store.sqlite`) / Postgres (disjoint tables in the same prod DB).
- **Purpose:** the **checkpointer** holds chat message history per thread; the **store** backs the agent's dynamic `/memories/` cross-thread scratch files (namespaced per user).

### 4.3. Agent workspace files
- **Sandbox ON:** a **durable Docker named volume per workspace** (`joyjoy-ws-<id>`), mounted at `/workspace`; outlives the ephemeral container.
- **Sandbox OFF:** host dir `WORKSPACE_ROOT/<uid>/workspace/<workspace_id>` (`.env`: `WORKSPACE_ROOT=…/data/workspaces`). The **only** on-disk app state in host mode.

## 5. External Integrations / APIs

- **Model providers** — Azure OpenAI, Anthropic (+ Azure AI Foundry `/anthropic` Claude), AWS Bedrock, OpenAI-compatible (OpenAI/OpenRouter/DeepSeek/Groq/local via `base_url`), Google Gemini. **Integration:** provider-specific LangChain SDKs; keys Fernet-encrypted in the DB, managed in Settings→Providers.
- **MCP servers** — jira/Atlassian, DuckDuckGo web-search, workspace-fs (file delete/move/mkdir), joyjoy-demo. **Integration:** Model Context Protocol over HTTP/stdio (`langchain-mcp-adapters`); secrets passed as `${VAR}` refs, never stored.
- **OpenSandbox** — code/shell/file execution. **Integration:** `opensandbox` SDK → server on `:8090`.
- **SMTP (optional)** — password-reset OTP email; unset in dev logs the OTP instead.

## 6. Deployment & Infrastructure

- **Dev:** WSL2 + Docker; `bash scripts/start_all.sh` (self-bootstrapping: `uv sync`, `npm install`, build sandbox image, build SPA, start sandbox+jira+backend).
- **Containerized:** `docker-compose.yml` brings up Postgres + the app (`docker compose up --build`, `:8080`); schema + seed auto-load on first boot. (Compose does **not** include the OpenSandbox layer.)
- **Prod:** `APP_ENV=prod` + `DATABASE_URL=postgresql://…`; the app DB and LangGraph checkpointer share one Postgres database via disjoint tables. Agent files = the only on-disk state (point `WORKSPACE_ROOT` at a shared mount for multi-node).
- **CI/CD:** none committed yet.
- **Monitoring/Logging:** stdout logs (`/tmp/joyjoy_*.log` in dev); no APM wired.

## 7. Security Considerations

- **Authentication:** username/password accounts (bcrypt) → **httpOnly signed-JWT session cookie** (`sub = User.id`); also accepts a bearer JWT / `X-User-Id` (the header is only trusted in dev or behind a configured `GATEWAY_API_KEY`). Password reset via hashed, expiring, single-use OTP.
- **Authorization:** per-user data keyed by `User.id` with owner checks; **global catalogs are read-only** (writes to a global id are rejected); a user's effective capabilities = global ∪ their own.
- **Encryption:** TLS in transit (at the deploy tier); **Fernet (AES) at rest** for model/provider secrets (`CREDENTIAL_ENCRYPTION_KEY`, generate-once). The seed SQL carries only `${VAR}` env-refs — no plaintext secret committed; `describe_models` masks keys to the browser.
- **Execution isolation:** agent code runs in OpenSandbox containers (Docker; gVisor/runsc is the prod-hardening step), per-`(user, thread)`, with egress controls available.
- **Tool safety:** all MCP tools (+ `execute`) are **HITL-gated** in the runs API; users opt into per-chat auto-approve (`Session.auto_approve` / account default).

## 8. Development & Testing Environment

- **Local setup:** see `README.md` / `CLAUDE.md`. Prereqs: Docker, `uv`, Node 22 (WSL2 on Windows). One command: `bash scripts/start_all.sh`.
- **Lint/format:** backend `ruff` (`uv run ruff check/format app`); frontend `biome` + `tsc` (`npx biome check src`, `npx tsc --noEmit`) — both must be clean before `npm run build`. i18n locales must be key-parity with `en.ts`.
- **Testing:** no substantive pytest suite yet (deps present as dev extras). `scripts/validate_models.py` is the main standalone check (model specs + `${VAR}` resolution); behavior is validated against the live `/v1` API with a real session cookie. Never `import app.main` from a standalone script (it opens a DB connection at import).

## 9. Future Considerations / Roadmap

- **gVisor/runsc** runtime for the sandbox (prod hardening; currently `runc`).
- **Multi-node:** the in-process `_RUNS`/HITL approval registry and the single-process workspace assume one node — needs a shared store + shared workspace mount to scale out.
- **Migrations discipline:** dev relies on `create_all` (which won't ALTER existing tables) + ad-hoc `ALTER`; prod schema changes must go through Alembic.
- **Test suite:** add real pytest/httpx coverage for `/v1` + the agent CRUD paths.

## 10. Project Identification

- **Project Name:** joyjoy
- **Repository:** local at `~/joyjoy` (WSL); private/internal.
- **Primary Contact:** Gouranga Satapathy (gouranga.satapathy@sapiens.com)
- **Date of Last Update:** 2026-06-24

## 11. Glossary / Acronyms

- **Deep Agent / deepagents:** the agent framework (filesystem/skills/memory middleware over LangGraph) compiled via `create_deep_agent()`.
- **LangGraph checkpointer / store:** persistence for chat message state (checkpointer) and cross-thread agent memory (store).
- **MCP (Model Context Protocol):** standard for out-of-process tool servers; loaded via `langchain-mcp-adapters`.
- **HITL:** Human-In-The-Loop tool approval — gated tools pause for an approve/deny decision.
- **OpenSandbox / execd / fat image:** the container execution layer; `execd` is the in-container daemon; `joyjoy/sandbox-fat:<N>` is the multi-language image (Python/Node/Java/Go/Rust/C/C++ + browser/data/doc tooling).
- **workspace_id / thread_id:** a chat's identity; the workspace_id keys its files (host dir or Docker volume); forks share a workspace.
- **SPA:** the React single-page app, served by the backend from `frontend/dist`.
- **Fernet:** symmetric encryption (cryptography lib) used for secrets-at-rest.
- **APP_ENV:** `dev` (SQLite) vs `prod` (Postgres) selector.
