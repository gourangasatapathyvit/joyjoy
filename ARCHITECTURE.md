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
├── docker-compose.yml         # baked stack: backend(:8080) + profile-gated infra (localdb/sandbox/observability)
├── docker-compose.dev.yml     # infra only (no backend) — run the backend on the host
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

Which backend is used is set by `COMPOSE_PROFILES` (`Settings.db_mode`): `devdb` → SQLite; `localdb`/`server` → Postgres.

| Store | `devdb` | `localdb`/`server` | Holds |
|-------|-----|------|-------|
| **Relational app DB** (SQLAlchemy 2.0 async) | SQLite `./data/joyjoy.db` | Postgres `APP_DB_NAME` (`joyjoy_db`) | Accounts, config, catalogs, per-user skills/MCP/models, sessions |
| **LangGraph checkpointer** | SqliteSaver | PostgresSaver — **separate** DB `LANGGRAPH_CHECKPOINT_DB` (`langgraph_db`) | **Chat message history** + run state (the only place messages live) |
| **Workspace files** | `./data/...` | `/data` Docker volume (`WORKSPACE_ROOT`) | Agent's real files per `<uid>/workspace/<thread>` — only on-disk app state in the baked stack |
| **OpenSandbox volumes** (opt-in) | — | docker named volume per `workspace_id` | Durable per-session sandbox FS when the `sandbox` profile is active. `workspace_id` for a brand-new session is minted as `{user_id}-{thread_id}` (`_mint_workspace_id`, `app/stores/sessions.py`) so the volume name is structurally per-user, not just app-logic-checked |

**Relational schema** (`backend/app/db/models.py`) — surrogate string-UUID PKs:
- **Accounts**: `users`, `password_resets`.
- **Global catalogs** (seeded on first boot from `app/db/seeds/global_seed.sql`, read-only in UI): `skins`, `global_providers`, `global_models`, `global_skills`, `global_mcps`, `skill_files`.
- **Per-user**: `user_configs` (theme/skin/locale/default model/memory `agents_md`/auto-approve default…), `user_models`, `user_skills`, `user_mcps`.
- **Conversations**: `sessions` (`thread_id` PK = LangGraph thread; `user_id`, `title`, `default_model`, `reasoning`, `auto_approve`, `pinned`, `workspace_path`, `forked_from`, `meta` = usage+sources telemetry).
- **Secrets at rest**: secret fields inside `settings` JSON columns are **Fernet-encrypted** (`db/crypto.py`, `CREDENTIAL_ENCRYPTION_KEY`).
- **Migrations**: Alembic.

---

## 5. External Integrations / APIs

- **Model providers** (LangChain SDKs; dispatched by `provider` in each model spec): Azure OpenAI, Anthropic (incl. Azure AI Foundry `/anthropic` Claude endpoint), AWS Bedrock (`langchain-aws`/boto3), Google GenAI, NVIDIA NIM (`langchain-nvidia-ai-endpoints`'s `ChatNVIDIA`), and any OpenAI-compatible endpoint (OpenAI itself, OpenRouter, DeepSeek, Groq, local servers — via a configurable base URL). Catalog = `global_models` + per-user `user_models`; keys referenced as `${VAR}` and expanded at build (kept out of the DB seed). **Policy**: a provider with its own official LangChain package gets a dedicated `Provider` + `build_model_for` branch (NVIDIA is the first) rather than being folded into the generic OpenAI-compatible bucket — the dedicated package's own capability metadata beats hand-verifying via id heuristics or live trial-and-error.
- **Dynamic model discovery**: instead of hand-typing a model id, the Providers tab can call `POST /v1/models/config/discover` with the entered credentials to list a provider's live catalog (`agent.py`'s per-provider adapters — `httpx` for OpenAI/Gemini/Anthropic/Azure REST list-models calls, `boto3` for Bedrock's `list_foundation_models`, `ChatNVIDIA.get_available_models()` for NVIDIA), then bulk-save a multi-selected subset via `POST /v1/models/config/save-bulk`. NVIDIA's adapter is the one with REAL per-model capability flags (`supports_tools`/`supports_thinking`/`supports_structured_output`) rather than guessing from the model id string like the others still do. Per-user model ids are **provider-qualified composites** (`{provider}:{raw_id}`, e.g. `openai:gpt-4.1`) so the same base model name can exist under different providers without colliding with a global model or another user model — global (seeded) ids stay bare. Discovery re-uses a model's own stored (decrypted) credentials when editing, so switching a model's underlying deployment doesn't require retyping the API key.
- **MCP servers** (`langchain-mcp-adapters`, stdio + streamable-http): configured in `global_mcps` + `user_mcps`. Examples: `joyjoy_demo` (demo `joyjoy_ping`), `jira` (mcp-atlassian over http), `web-search` (DuckDuckGo via `uvx`). `${VAR}` expansion in command/args/url/headers/env; stdio servers get PATH/HOME/cache injected. **All MCP/plugin tools auto-gate for HITL approval.** `describe_mcp` returns the original `${VAR}` refs — never the expanded secret.
- **SMTP** (optional): password-reset OTP email; when unset, the OTP is logged (dev).

---

## 6. Deployment & Infrastructure

- **Image**: one multi-stage Dockerfile — Stage 1 `node:22` builds the SPA; Stage 2 `python:3.13-slim` installs the backend (`uv pip install -e .`), copies `frontend/dist`, runs `uvicorn` on `:8080`. Includes `uv`/`uvx` (for uvx MCPs) + headless LibreOffice (office previews).
- **Compose** (`docker-compose.yml`, network `joyjoy-net`): the `backend` service always runs; every other service is gated behind a profile. **`COMPOSE_PROFILES` is the single switch** — the backend self-derives its DB mode, sandbox, and metrics/tracing from it (no separate `SANDBOX_ENABLED`/`METRICS_ENABLED`/`TRACING_ENABLED` flags); `DEV_MODE` (default `false` in the image) separately toggles auth strictness.
  - `backend` *(no profile — always on)* — the app; volume `workspaces:${CONTAINER_DATA_DIR:-/data}`; healthcheck `GET /v1/health`. `WORKSPACE_ROOT`/`APP_DB_PATH`/`SQLITE_CHECKPOINT_PATH` inside the container all derive from the same `CONTAINER_DATA_DIR` as the volume mount, so `devdb` mode's SQLite files (and the workspace files) survive `docker compose up --build` instead of living on the container's ephemeral writable layer.
  - **DB backend** (pick one, or none): **`localdb`** → bundled Postgres 16 (`db` service), which creates two databases on first init (`APP_DB_NAME` + the separate `LANGGRAPH_CHECKPOINT_DB` via `scripts/db-init`); **`devdb`** → no Postgres, local SQLite; **neither** → external Postgres from the `DB_*` vars (there is intentionally no `depends_on`).
  - **`sandbox` profile** — the code-execution tier: `opensandbox` server + `docker-socket-proxy` (least-privilege daemon access) + `sandbox-image` (build-only). The profile alone enables sandbox mode in the backend. Spawned sandboxes live on the isolated `joyjoy-sandbox-net` (cannot reach backend/DB).
  - **`observability` profile** — metrics + tracing stack (see §7a): self-hosted **Langfuse** (`langfuse-web`/`-worker` + `-postgres`/`-clickhouse`/`-redis`/`-minio`) for traces, and **Prometheus** + **Grafana** for metrics (config under `observability/`). The profile alone flips the backend's metrics + tracing on.
  - Profiles compose freely: e.g. `COMPOSE_PROFILES=localdb,sandbox,observability docker compose up --build` runs backend + bundled Postgres + the sandbox tier + the observability stack.
- **Dev-infra compose** (`docker-compose.dev.yml`): the same profile-gated infra with **no `backend` service** — for the workflow where the developer builds the SPA and runs the backend on the host. `scripts/dev-up.sh` picks this file vs the baked `docker-compose.yml` based on `DEV_MODE` in `.env`.
- **Secrets** via `.env` (compose interpolation): `JWT_SECRET`, `CREDENTIAL_ENCRYPTION_KEY` (generate-once, must stay stable), `AZURE_OPENAI_API_KEY`, and the `DB_*` vars in `server` db mode.
- **Dev (WSL)**: `scripts/start_all.sh` brings up jira MCP (`:9000`) → backend (`:8080`) in order; idempotent. `DEV_MODE=true` + `devdb` = SQLite + no-auth dev user.
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

## 7a. Observability

Two independent, env-gated layers — both off by default, both no-ops unless enabled. Wiring lives in `app/core/observability.py`; the backing stack ships as the `observability` compose profile (see §6).

**Tracing → self-hosted Langfuse, attributed per-user + per-session.** deepagents runs on LangChain, so its native tracer captures every graph node / LLM call / tool call with **no code**. `setup_tracing()` picks one of two transports by what's configured:
- **(A) Langfuse LangChain callback — preferred** (when `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` are set). `trace_config()` stamps each run's metadata with `langfuse_user_id` (the tenant) and `langfuse_session_id` (the thread = the chat), which the handler maps to Langfuse's **native User + Session fields** → real per-user analytics and per-session (session-label) grouping/replay. The handler is attached per run via `langchain_callbacks()`.
- **(B) OTLP bridge — fallback** (when no Langfuse keys, but `OTEL_EXPORTER_OTLP_ENDPOINT` is set): LangSmith's OTEL export → any OTLP collector (Tempo/Jaeger too). Vendor-neutral, but user/thread arrive as generic metadata, not native fields. Requires `opentelemetry-sdk` + the OTLP HTTP exporter.
- Enabled automatically by `COMPOSE_PROFILES=observability` (no separate `TRACING_ENABLED` flag; set it explicitly only to override). The same profile headless-bootstraps the Langfuse project with the same keys (`LANGFUSE_INIT_*`), so per-user/session tracing works on first boot with no manual key-copy.

> **Granularity:** per-user and per-session live in **tracing** (Langfuse User/Session), NOT in metric labels — Prometheus labels stay bounded (model/tool/decision) to avoid cardinality blow-up.

**Metrics → Prometheus + Grafana.** Enabled automatically by `COMPOSE_PROFILES=observability` (no separate `METRICS_ENABLED` flag). Exposes `/metrics` and instruments:
- HTTP (pure-ASGI `RequestMetricsMiddleware`, so SSE isn't buffered): request count + latency by method/templated-path/status.
- Agent runs (in `runs.py`): runs total/errors, end-to-end latency, active-runs gauge, token totals (from `usage_metadata`), HITL approval decisions.
- LLM/tool calls (a `PrometheusCallbackHandler` attached per run via the run config): call counts + latencies, tool errors.
- Label cardinality is bounded on purpose (`model`/`tool`/`decision` are small sets); per-user/thread detail lives in traces, never metric labels. Prometheus scrapes `backend:8080/metrics` (`observability/prometheus.yml`); Grafana auto-provisions the datasource (`observability/grafana/`).

---

## 8. Development & Testing Environment

- **Backend**: Python ≥3.11, `uv` for deps; run `uvicorn app.main:app` (or `scripts/run-backend.sh`). Tests: `pytest` (asyncio mode) in `backend/tests`. Lint: `ruff`. Migrations: `alembic`.
- **Frontend**: Node 22; `npm run dev` (Vite `:5173`), `npm run build` (`tsc -b && vite build`), `npm run check` (Biome lint+format). Strict TypeScript.
- **Dev defaults**: `DEV_MODE=true` + `COMPOSE_PROFILES=devdb` → SQLite app DB + SQLite checkpointer + no-auth dev user. Browse via Vite `:5173` (proxy injects `X-User-Id`) or the baked SPA on `:8080`.
- **Full local stack**: `COMPOSE_PROFILES=localdb docker compose up --build` (bundled Postgres), the infra-only `docker compose -f docker-compose.dev.yml up -d`, or `scripts/start_all.sh` in WSL.

---

## 9. Future Considerations / Roadmap

- **Sandbox prod hardening**: finalize gVisor (`runsc`) runtime config; the OpenSandbox-in-compose networking is a scaffold and needs per-host validation (the proven dev path runs the server on the host).
- **Node-based MCPs in WSL**: bare `npx` resolves to Windows `npx` (CMD/UNC failures) — prefer `uvx`/Python MCP servers until a Linux Node is installed.
- **Observability**: DONE — opt-in metrics (Prometheus + Grafana, with a provisioned **joyjoy — Overview** dashboard) and tracing (self-hosted Langfuse, native per-user/session) ship as the `observability` compose profile (see §7a). Still possible: Grafana alerting rules.
- **CI/CD**: no pipeline codified yet (deferred). Natural next step: GitHub Actions running backend `ruff`+`pytest` and frontend `biome`+`tsc`+`vite build`, optionally building/pushing the image.
- **Multi-node**: workspace files must move to a shared mount (point `WORKSPACE_ROOT` at NFS/EFS/SMB); checkpointer already Postgres-backed.

---

## 10. Project Identification

- **Name**: joyjoy — multi-tenant Deep Agents platform.
- **Repository**: local working tree at `~/joyjoy` (WSL). Backend `joyjoy-backend`, frontend `frontend`.
- **Primary entry points**: `backend/app/main.py` (API + SPA), `frontend/src/main.tsx` (SPA).
- **Runtime port**: `:8080` (single origin for SPA + `/v1` API).
- **Last updated**: 2026-07-15.

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
- **Composite model id**: a per-user model's catalog key, `{provider}:{raw_id}` (e.g. `openai:gpt-4.1`), so the same base model name can exist under multiple providers without colliding. Global (seeded) model ids stay bare.
```
