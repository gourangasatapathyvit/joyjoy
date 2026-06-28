# ARCHITECTURE.md

> Living architecture overview for **joyjoy** — a multi-tenant Deep Agents platform.
> Format follows the [architecture.md](https://architecture.md/) template (11 sections).
> Keep this file in sync as the codebase evolves.

joyjoy is a **single FastAPI process** that serves a **React SPA** and a **`/v1` JSON/SSE API** on one port (`:8080`). Each user gets a private, isolated agent workspace, long-term memory, skills, and MCP tools. One compiled agent per `(run/chat, user, model, reasoning, genui)` is cached in-process; every request carries its own `user_id` + `thread_id` for tenant isolation.

---

## 1. Project Structure

```
joyjoy/
├── Dockerfile                 # multi-stage: node:22 builds SPA → python:3.13-slim runs uvicorn + serves dist
├── docker-compose.yml         # backend(:8080) + optional localdb (profile) + optional sandbox (profile)
├── sandbox.toml               # OpenSandbox server config (runtime/egress/network hardening)
├── ARCHITECTURE.md  CLAUDE.md  README.md
├── scripts/                   # start_all.sh, run_atlassian_wsl.sh, install_{bedrock,gemini}.sh, run-backend.sh …
├── data/workspaces/           # dev agent workspace files (prod → /data volume)
│
├── backend/                   # FastAPI + deepagents + LangGraph (Python 3.11+)
│   ├── pyproject.toml         # deps: deepagents, langgraph, langchain-*, fastapi, sqlalchemy, psycopg, alembic …
│   ├── alembic/               # DB migrations (baseline)
│   ├── static/                # brand assets / favicons served at /static
│   ├── mcp_servers/           # bundled MCP servers (joyjoy_demo.py, workspace_fs)
│   └── app/
│       ├── main.py            # app assembly + lifespan (env load, DB init/seed, persistence, agent warm-up, SPA mount)
│       ├── core/              # config.py (Settings), auth.py, context.py, constants, enums, text/time utils
│       ├── db/                # models.py (SQLAlchemy schema), engine.py, crypto.py (Fernet), seed.py, seeds/*.sql
│       ├── agent/             # agent.py (build+cache), prompts.py, middleware.py, runs.py (SSE+HITL), agent_common.py
│       ├── routes/            # one APIRouter per concern: auth, models, mcp, skills, memory, workspace,
│       │                      #   settings_ui, chat, runs, sessions, health (+ deps.py)
│       ├── stores/            # sessions, users, usersettings, skills_store, mcp_runtime, memory_store,
│       │                      #   persistence (checkpointer/store), dbfs (DB→agent-FS bridge)
│       ├── workspace/         # workspace.py (per-thread files), media.py (/v1/media; office→PDF)
│       └── sandbox/           # OpenSandbox integration (opt-in code/shell execution)
│
└── frontend/                  # React 19 + Vite 8 SPA (assistant-ui external store)
    ├── package.json           # assistant-ui, tailwind v4, zustand, tanstack-query, react-router 7, biome
    └── src/
        ├── main.tsx  App.tsx  providers.tsx
        ├── runtime/           # JoyjoyRuntimeProvider.tsx (external-store runtime + custom SSE), workspaceAttachment.ts
        ├── routes/            # ChatPage, SettingsPage, McpPanel, SkillsPanel, MemoryPanel, ProvidersPanel, AuthPage
        ├── components/
        │   ├── assistant-ui/  # thread, tool-uis, generative-ui, html-canvas, reasoning, media-part, dot-matrix …
        │   ├── chat/          # ConversationSidebar, ModelPicker, WorkspaceDock, DownloadButton
        │   ├── layout/        # AppShell, PanelLayout, ConnectionStatus
        │   ├── memory/ skills/ settings/ auth/ ui/(shadcn)
        ├── store/             # zustand: chat.ts, settings.ts
        ├── api/               # client.ts, queries.ts (TanStack), sessions, auth, workspace, types …
        └── i18n/              # config + 16 locale files (strict Resources = typeof en)
```

---

## 2. High-Level System Diagram

```
                         ┌──────────────────────────────────────────────┐
  Browser (SPA)          │            joyjoy backend  (:8080)            │
  React 19 + assistant-ui│                                               │
  external-store runtime │  FastAPI app (single process, many users)     │
        │  HTTPS          │   ├─ /static, /favicon, SPA (app.frontend()) │
        │  cookie auth    │   ├─ /v1/* routers (auth, models, mcp,       │
        ├────────────────►│   │     skills, memory, workspace, settings, │
        │  POST /v1/runs  │   │     chat, runs, sessions, health)        │
        │◄──── SSE ───────│   └─ Agent engine (deepagents + LangGraph)   │
                          │        • per-(user,model,…) compiled-agent   │
                          │          cache  • HITL interrupt_on gating   │
                          └───────┬───────────────┬──────────────┬───────┘
                                  │               │              │
                       ┌──────────▼──┐   ┌────────▼───────┐  ┌───▼─────────────┐
                       │ Relational  │   │  LangGraph     │  │ Workspace files │
                       │ app DB      │   │  checkpointer  │  │ WORKSPACE_ROOT  │
                       │ (SQLite/PG) │   │  (chat history)│  │  /data volume   │
                       └─────────────┘   └────────────────┘  └─────────────────┘
                                  │
              ┌───────────────────┼─────────────────────┬───────────────────┐
        Model providers      MCP servers          SMTP (OTP)      OpenSandbox (opt-in)
     (Azure/Anthropic/        (stdio/http;                        per-session containers
      Bedrock/Google)      jira, web-search, …)                   on isolated network
```

Request shapes:
- **Chat/runs**: `POST /v1/runs` → agent streams tokens, tool calls, and approval interrupts back over **SSE** (`sse-starlette`). The SPA's `JoyjoyRuntimeProvider` is an assistant-ui **external-store** runtime fed by this custom SSE stream.
- **Everything else** (settings, skills, MCP CRUD, memory, workspace files, sessions) is plain JSON over `/v1/*`.

---

## 3. Core Components

### Backend — FastAPI app (`backend/app/main.py`)
- **Description**: Owns app creation + lifespan (load `.env` → resolve encryption key → `init_db` → `seed_all` → open persistence → warm the default agent → start the sandbox reaper). Mounts one `APIRouter` per concern and serves the built SPA via `app.frontend()` (FastAPI ≥0.138) with `fallback="auto"` for client-side routes.
- **Technologies**: FastAPI, uvicorn, CORS middleware.
- **Deployment**: single container, `uvicorn app.main:app` on `:8080`.

### Agent engine (`backend/app/agent/`)
- **Description**: `agent.py` builds and **caches** a compiled deepagents graph keyed `("run"|"chat", uid, model, effort, genui)`. Tools assembled per build = per-user MCP tools (cached, workspace-bound) + generative-UI tools (`render_ui`, `render_html` — gated by `genui`) + `load_skill` (sandbox only). `runs.py` drives the SSE run loop and **HITL approvals** (`interrupt_on` gates all MCP/plugin tools + configured built-ins + sandbox `execute`). `middleware.py` adds a thinking-block fix (`StripStaleThinkingMiddleware`) + production guards (call/tool limits, transient retry, context trimming) on top of deepagents' built-ins. Long-term memory (`AGENTS.md`) is injected by deepagents' `MemoryMiddleware`.
- **Technologies**: deepagents 0.6.11, langgraph ≥1.2, langchain-core, langchain-mcp-adapters.

### HTTP routers (`backend/app/routes/`)
- `auth` (signup/login/OTP/me), `models` (+providers), `mcp` (servers/tools CRUD), `skills` (global RO + user CRUD), `memory` (AGENTS.md + notes), `workspace` (file CRUD + raw), `settings_ui` (UI prefs), `chat`, `runs` (SSE + approvals + `/v1/capabilities`), `sessions` (per-user sidebar), `health`.

### Stores (`backend/app/stores/`)
- DB-backed accessors + the **DB→agent filesystem bridge** (`dbfs.py`: serves `/memory/AGENTS.md`, `/skills/*` from the DB into the agent's virtual FS). `persistence.py` opens the LangGraph checkpointer + store (SQLite dev / Postgres prod, pooled).

### Workspace + media (`backend/app/workspace/`)
- Real agent files live under `WORKSPACE_ROOT/<uid>/workspace/<thread>`. `media.py` serves `/v1/media` (same-origin, cookie-auth) and renders office docs → PDF via headless LibreOffice for inline previews. Generative-UI `workspace:<path>` refs resolve here.

### Frontend SPA (`frontend/src/`)
- **Description**: assistant-ui **external-store** runtime over a custom SSE client; routes for chat + settings panels (MCP, Skills, Memory, Providers); zustand stores for chat/UI state; TanStack Query for server cache; 16-locale i18n. Generative UI: `render_ui` → native `MessagePrimitive.GenerativeUI` component kit; `render_html` → sandboxed iframe HTML canvas with a `postMessage` bridge.
- **Technologies**: React 19, Vite 8, TypeScript, @assistant-ui/react, Tailwind v4 + shadcn/radix, zustand, @tanstack/react-query, react-router 7, i18next, Biome.
- **Deployment**: built to `frontend/dist`, copied into the backend image and served by FastAPI (no separate web server in prod). Dev: Vite on `:5173`.

---

## 4. Data Stores

| Store | Dev | Prod | Holds |
|-------|-----|------|-------|
| **Relational app DB** (SQLAlchemy 2.0 async) | SQLite `./data/joyjoy.db` | Postgres (`DATABASE_URL`) | Accounts, config, catalogs, per-user skills/MCP/models, sessions |
| **LangGraph checkpointer** | SqliteSaver | PostgresSaver (same PG) | **Chat message history** + run state (the only place messages live) |
| **Workspace files** | `./data/...` | `/data` Docker volume (`WORKSPACE_ROOT`) | Agent's real files per `<uid>/workspace/<thread>` — only on-disk app state in prod |
| **OpenSandbox volumes** (opt-in) | — | docker named volume per `workspace_id` | Durable per-session sandbox FS when `SANDBOX_ENABLED` |

**Relational schema** (`backend/app/db/models.py`) — surrogate string-UUID PKs:
- **Accounts**: `users`, `password_resets`.
- **Global catalogs** (seeded on first boot from `app/db/seeds/global_seed.sql`, read-only in UI): `skins`, `global_providers`, `global_models`, `global_skills`, `global_mcps`, `skill_files`.
- **Per-user**: `user_configs` (theme/skin/locale/default model/memory `agents_md`/auto-approve default…), `user_models`, `user_skills`, `user_mcps`.
- **Conversations**: `sessions` (`thread_id` PK = LangGraph thread; `user_id`, `title`, `default_model`, `reasoning`, `auto_approve`, `pinned`, `workspace_path`, `forked_from`, `meta` = usage+sources telemetry).
- **Secrets at rest**: secret fields inside `settings` JSON columns are **Fernet-encrypted** (`db/crypto.py`, `CREDENTIAL_ENCRYPTION_KEY`).
- **Migrations**: Alembic.

---

## 5. External Integrations / APIs

- **Model providers** (LangChain SDKs; dispatched by `provider` in each model spec): Azure OpenAI, Anthropic (incl. Azure AI Foundry `/anthropic` Claude endpoint), AWS Bedrock (`langchain-aws`/boto3), Google GenAI. Catalog = `global_models` + per-user `user_models`; keys referenced as `${VAR}` and expanded at build (kept out of the DB seed).
- **MCP servers** (`langchain-mcp-adapters`, stdio + streamable-http): configured in `global_mcps` + `user_mcps`. Examples: `joyjoy_demo` (demo `joyjoy_ping`), `jira` (mcp-atlassian over http), `web-search` (DuckDuckGo via `uvx`). `${VAR}` expansion in command/args/url/headers/env; stdio servers get PATH/HOME/cache injected. **All MCP/plugin tools auto-gate for HITL approval.** `describe_mcp` returns the original `${VAR}` refs — never the expanded secret.
- **SMTP** (optional): password-reset OTP email; when unset, the OTP is logged (dev).

---

## 6. Deployment & Infrastructure

- **Image**: one multi-stage Dockerfile — Stage 1 `node:22` builds the SPA; Stage 2 `python:3.13-slim` installs the backend (`uv pip install -e .`), copies `frontend/dist`, runs `uvicorn` on `:8080`. Includes `uv`/`uvx` (for uvx MCPs) + headless LibreOffice (office previews).
- **Compose** (`docker-compose.yml`, network `joyjoy-net`): the `backend` service always runs; the other services are gated behind **two optional, independent profiles** that can be enabled together via `COMPOSE_PROFILES=sandbox,localdb` (or singly, or neither):
  - `backend` *(no profile — always on)* — the app; `APP_ENV=prod`, reads `DATABASE_URL`; volume `workspaces:/data`; healthcheck `GET /v1/health`.
  - **`localdb` profile** — bundled Postgres 16 (`db` service) for local dev only; without it, prod points `DATABASE_URL` at a hosted Postgres (there is intentionally no `depends_on`).
  - **`sandbox` profile** — the opt-in code-execution tier: `opensandbox` server + `docker-socket-proxy` (least-privilege daemon access) + `sandbox-image` (build-only). Also set `SANDBOX_ENABLED=true` on the backend. Spawned sandboxes live on the isolated `joyjoy-sandbox-net` (cannot reach backend/DB).
  - Profiles compose freely: e.g. `COMPOSE_PROFILES=sandbox,localdb docker compose up --build` runs backend + bundled Postgres + the full sandbox tier; unset → backend only (hosted DB, host-workspace mode).
- **Secrets** via `.env` (compose interpolation): `JWT_SECRET`, `CREDENTIAL_ENCRYPTION_KEY` (generate-once, must stay stable), `AZURE_OPENAI_API_KEY`, `DATABASE_URL`.
- **Dev (WSL)**: `scripts/start_all.sh` brings up jira MCP (`:9000`) → backend (`:8080`) in order; idempotent. SQLite + no-auth dev user.
- **CI/CD & monitoring**: not yet codified in-repo (logs via stdout `logging`; healthcheck endpoint exists). *(see Roadmap)*

---

## 7. Security Considerations

- **Authentication**: username/password accounts (**bcrypt** hashes) + a **signed session cookie** (`joyjoy_session`, 30-day TTL); per-user **JWT** for direct/programmatic clients; password reset via hashed OTP. Dev-only no-auth fallback resolves the tenant from the `X-User-Id` header — **ignored in prod** (cookie/JWT only).
- **Multi-tenant isolation**: `User.id` (uuid) is the identity threaded through every per-user FK (CASCADE on delete); sessions, skills, MCP, models, workspace files, and memory are all user-scoped; `/v1/sessions` is filtered by owner.
- **Secrets**: Fernet-encrypted at rest; decrypted model/MCP keys live in **process memory only**; MCP descriptions never leak expanded `${VAR}` secrets.
- **HITL approvals**: in `run_mode`, `interrupt_on` gates **all** MCP/plugin tools (+ any `JOYJOY_INTERRUPT_TOOLS` built-ins + sandbox `execute`); the SPA shows an approval card; per-thread `auto_approve` (seeded from the account default) can bypass it.
- **Code execution sandbox** (opt-in, layered): isolated container per session; daemon access via filtering proxy (no raw `docker.sock`); sandboxes on a network with no route to backend/DB; runtime/egress hardening in `sandbox.toml` (gVisor/kata, AppArmor, nft egress).
- **Generative-UI HTML canvas**: agent-authored HTML runs in a **sandboxed `<iframe sandbox="allow-scripts">`** (no `allow-same-origin` → opaque origin, no cookies/DOM/workspace access), strict CSP (`default-src 'none'`), talking to the app only through a source-validated `postMessage` bridge (`window.aui.{send,compose,link}`).

---

## 8. Development & Testing Environment

- **Backend**: Python ≥3.11, `uv` for deps; run `uvicorn app.main:app` (or `scripts/run-backend.sh`). Tests: `pytest` (asyncio mode) in `backend/tests`. Lint: `ruff`. Migrations: `alembic`.
- **Frontend**: Node 22; `npm run dev` (Vite `:5173`), `npm run build` (`tsc -b && vite build`), `npm run check` (Biome lint+format). Strict TypeScript.
- **Dev defaults**: `APP_ENV=dev` → SQLite app DB + SQLite checkpointer + no-auth dev user. Browse via Vite `:5173` (proxy injects `X-User-Id`) or the baked SPA on `:8080`.
- **Full local stack**: `docker compose --profile localdb up --build` (bundled Postgres), or `scripts/start_all.sh` in WSL.

---

## 9. Future Considerations / Roadmap

- **Sandbox prod hardening**: finalize gVisor (`runsc`) runtime config; the OpenSandbox-in-compose networking is a scaffold and needs per-host validation (the proven dev path runs the server on the host).
- **Node-based MCPs in WSL**: bare `npx` resolves to Windows `npx` (CMD/UNC failures) — prefer `uvx`/Python MCP servers until a Linux Node is installed.
- **CI/CD + observability**: no pipeline or metrics/tracing stack codified yet (only stdout logging + `/v1/health`).
- **Multi-node**: workspace files must move to a shared mount (point `WORKSPACE_ROOT` at NFS/EFS/SMB); checkpointer already Postgres-backed.

---

## 10. Project Identification

- **Name**: joyjoy — multi-tenant Deep Agents platform.
- **Repository**: local working tree at `~/joyjoy` (WSL). Backend `joyjoy-backend`, frontend `frontend`.
- **Primary entry points**: `backend/app/main.py` (API + SPA), `frontend/src/main.tsx` (SPA).
- **Runtime port**: `:8080` (single origin for SPA + `/v1` API).
- **Last updated**: 2026-06-28.

---

## 11. Glossary / Acronyms

- **Deep Agent / deepagents**: the agent framework (planning + filesystem + memory + skills + subagents) built on LangGraph; joyjoy compiles one per `(user, model, …)`.
- **LangGraph**: stateful agent runtime; its **checkpointer** persists chat/run state (here = the message store).
- **MCP** (Model Context Protocol): standard for external tool servers (stdio/http) loaded via `langchain-mcp-adapters`.
- **HITL**: Human-In-The-Loop — tool-call approval gating (`interrupt_on` + approval cards; per-thread `auto_approve`).
- **Skill**: a Markdown (`SKILL.md`) capability bundle (+ files); global (read-only) or per-user; materialized into the agent's FS.
- **Skin**: a named UI theme/accent set (global catalog) selectable per user.
- **Workspace**: a thread's on-disk file area (`WORKSPACE_ROOT/<uid>/workspace/<thread>`); surfaced in the UI dock and via `/v1/media`.
- **OpenSandbox**: opt-in per-session container providing isolated code/shell execution and a durable volume.
- **Generative UI**: agent-emitted rich UI — `render_ui` (JSON component kit, native assistant-ui renderer) and `render_html` (sandboxed HTML-canvas iframe). Gated per session by the `genui` flag.
- **External-store runtime**: assistant-ui mode where chat state is owned by the app (zustand + custom SSE) rather than a built-in runtime.
```
