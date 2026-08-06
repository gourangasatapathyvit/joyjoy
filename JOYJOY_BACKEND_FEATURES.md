# Joyjoy Backend — Feature Inventory

Multi-tenant **Deep Agents** backend: one **FastAPI** process serves the React SPA and the **`/v1` JSON/SSE API** on `:8080`. One compiled agent is cached per `(run|chat, user, model, reasoning, genui)`; every request carries `user_id` + `thread_id` for isolation.

---

## 1. Platform / process model

| Feature | What it does |
|---|---|
| **Single process, many users** | One uvicorn app; no per-user process |
| **SPA + API same origin** | Serves `frontend/dist` + `/v1/*` on `:8080` |
| **Profile-driven config** | `COMPOSE_PROFILES` derives DB mode, sandbox, observability |
| **Dev vs prod auth** | `DEV_MODE=true` → `X-User-Id` no-auth; `false` → cookie/JWT only |
| **Lifespan boot** | Load `.env` → crypto key → DB init/seed → checkpointer → agent warm-up → sandbox reaper |
| **Runtime path injection** | `${JOYJOY_PYTHON}` / `${JOYJOY_UVX}` / `${JOYJOY_BACKEND}` for portable MCP rows |
| **Health endpoints** | `/healthz`, `/health`, `/health/detailed`, `/v1/health` |
| **Static / favicon** | Brand assets at `/static`, favicons |

---

## 2. Authentication & identity

- **Signup** / **login** / **logout**
- **bcrypt** password hashes
- **Signed session cookie** (`joyjoy_session`, long TTL)
- **Bearer JWT** for programmatic clients
- **Optional gateway key** verification
- **`GET /v1/auth/me`** — current user
- **`GET /v1/auth/available`** — username availability
- **Forgot password** → OTP (SMTP when configured; logged in dev)
- **Reset password** (hashed OTP, attempt limits, expiry)
- **Change password** (authenticated)
- Multi-tenant identity = `User.id` (UUID) on every per-user FK (CASCADE delete)

---

## 3. Agent engine (deepagents + LangGraph)

### Build & cache

- Compiled graphs cached by `("run"|"chat", uid, model, effort, genui)`
- Cache invalidate after skills / MCP / models / memory writes
- Separate **chat** vs **run** agent modes
- Default-agent warm-up on boot

### Tools assembled at build

- **Deepagents built-ins**: filesystem (`read_file`, `write_file`, `edit_file`, `ls`, `glob`, `grep`), `execute` (sandbox), todos, subagents (`task`), summarization, memory, skills loading, HITL middleware, etc.
- **Per-user MCP tools** (cached, workspace-bound)
- **`render_ui` / `render_html`** — native in-process `StructuredTool`s (not MCP); gated by `genui`
- **`load_skill`** — sandbox-only skill loader
- Session workspace binding for tools

### Run loop (`POST /v1/runs` + SSE)

- Stream tokens, tool calls, tool progress, usage, sources
- **HITL interrupts** → `approval.request` events
- **Approval respond** API (`approve` / deny / always-style choices handled in loop)
- **Cancel run**
- **Auto-approve** per run or account default
- **Edit/regenerate**: `replace_turns` truncates trailing user turns before append
- Per-thread session recording (title, model, reasoning, workspace, auto_approve)
- Telemetry in session `meta`: usage + sources (survives reload)
- Reasoning text extraction for live stream **and** message reload serialization

### Capabilities advertisement

`GET /v1/capabilities` → approval events, tool progress, sandbox enabled + mount path

### OpenAI-style chat (compat)

`POST /v1/chat/completions` — streaming chat completions path (non-HITL style)

---

## 4. HITL (human-in-the-loop)

- In run mode, `interrupt_on` gates:
  - **All MCP / plugin tools**
  - Built-ins listed in `JOYJOY_INTERRUPT_TOOLS`
  - Sandbox **`execute`**
- Per-thread `auto_approve` bypass
- Account default `auto_approve_default` for new chats
- Multi-tool interrupt rounds in one turn supported

---

## 5. Middleware / production guards

Additive over deepagents’ stack:

| Middleware | Role |
|---|---|
| **ModelCallLimitMiddleware** | Cap model calls per turn; end gracefully |
| **ToolCallLimitMiddleware** | Cap tool calls per turn |
| **StripStaleThinkingMiddleware** | Drop signature-only thinking blocks (Azure Foundry Claude multi-turn fix) |
| **ContextEditingMiddleware** | Prune old tool results when context is huge |
| **ModelRetryMiddleware** | Transient-only retry (408/429/5xx, timeouts) with jittered backoff |

Also: deepagents Memory / Summarization / SubAgent / Filesystem / Skills / HITL / PromptCaching, etc.

---

## 6. Model providers & catalog

### Supported providers (`Provider` enum)

| Provider | Integration |
|---|---|
| **azure_openai** | Azure OpenAI deployments |
| **anthropic** | Anthropic + Azure AI Foundry `/anthropic` |
| **bedrock** | AWS Bedrock (`langchain-aws` / boto3) |
| **openai** | OpenAI-compatible (OpenAI, OpenRouter, DeepSeek, Groq, local) |
| **gemini** | Google GenAI |
| **nvidia** | NVIDIA NIM (`ChatNVIDIA`) — real capability flags |
| **xai** | xAI Grok API key (`ChatXAI`) |
| **xai_oauth** | xAI device-code OAuth (SuperGrok / X Premium+) |

### Model APIs

- List merged global + user models
- Provider config schemas for Add/Edit forms
- **Save** / **delete** user models
- **Discover** live catalog (`POST …/discover`)
- **Bulk save** discovered models (`…/save-bulk`)
- **Test** model (incl. reasoning probe that requires **visible** reasoning text, not mere non-error)
- Composite user model ids: `{provider}:{raw_id}` (no collide with global bare ids)
- Secrets as `${VAR}` refs expanded at build; masked in API responses
- Reasoning effort normalize + per-model `supports_reasoning` gating
- Persist discovered reasoning capability flag on user model

### xAI OAuth specifically

- RFC 8628 device-code: `/v1/models/config/xai-oauth/start` + `/poll`
- Access token used as API bearer
- Refresh on **every** agent build lookup (cache has no TTL)
- Per-model lock (xAI rotates refresh token each use)
- Token persist invalidates user agent cache

---

## 7. Sessions / conversations

| API | Behavior |
|---|---|
| `GET /v1/sessions` | Per-user list (pinned first) |
| `POST /v1/sessions` | Create |
| `GET …/messages` | Load history from **LangGraph checkpointer** (incl. reasoning) |
| `POST /v1/sessions/import` | Import message list → new session |
| `PATCH /v1/sessions/{id}` | Title, pin, model, reasoning, auto_approve, … |
| `DELETE /v1/sessions/{id}` | Delete session + checkpoint data |

Also:

- Auto title from first user text
- **Workspace id** mint: `{user_id}-{thread_id}` (ownership-checked; no cross-tenant fallback)
- **Fork session** support in store
- Session meta: usage + sources telemetry
- `forked_from` lineage field

**Messages live only in the LangGraph checkpointer**, not the relational DB.

---

## 8. MCP servers

- Merge **global** + **per-user** MCP configs
- Transports: **stdio** and **streamable HTTP**
- CRUD: list servers, list tools, put/save, delete, toggle enable
- `${VAR}` expansion in command/args/url/headers/env
- stdio gets PATH/HOME/cache injection
- Status: configured / active / invalid_config / disabled
- `describe_mcp` never returns expanded secrets
- Tools loaded via `langchain-mcp-adapters`, bound to session workspace
- Bundled / seeded:
  - `joyjoy-demo` (stdio)
  - `workspace-fs` (stdio)
  - `web-search` (DuckDuckGo via `uvx`)
  - `jira` (HTTP, seeded disabled)

---

## 9. Skills

- Global catalog (**~73 seeded** community/skills, read-only) + per-user skills
- List / get content / save / delete / toggle enable
- Helper **skill files** tree (scripts, references, …) — save/delete
- **Import zip** of a skill package
- DB → agent FS bridge serves `/skills/*`
- Sandbox `load_skill` for on-demand loading

---

## 10. Memory

- Core **AGENTS.md**-style memory on `user_configs.agents_md` (always loaded via MemoryMiddleware)
- Extra **memory files** under `/memories/` (list / read / write / delete / toggle)
- Editable by UI **and** agent (`edit_file` on virtual FS)
- DB → agent FS bridge (`stores/dbfs.py`)

---

## 11. Workspace & media

### Workspace files

Per-user, per-thread under `WORKSPACE_ROOT/<uid>/workspace/<thread>` (or sandbox volume when enabled):

- Tree listing
- Read file (text/binary metadata)
- Save / mkdir / delete / rename
- Upload multipart
- Raw stream / download

When sandbox profile is on, file ops go through **OpenSandbox volume** backends.

### Media (`/v1/media`)

- Cookie-auth same-origin media serving
- Path resolution with safe roots (tenant isolation)
- **Office → PDF** via headless LibreOffice for inline preview
- `workspace:` path resolution for generative UI / chat media
- Media extraction helpers from messages

---

## 12. Sandbox (opt-in `sandbox` profile)

- **OpenSandbox** integration for code/shell `execute`
- Per-session containers on isolated network (no route to backend/DB)
- Named volume per `workspace_id` (structurally `{user}-{thread}`)
- Acquire / renew / pause / kill session
- **Cap enforcement** on concurrent sandboxes
- Background **reaper** for idle sandboxes
- Health probe
- docker-socket-proxy + hardened `sandbox.toml` (runtime/egress)
- Workspace materialize into sandbox FS

---

## 13. Settings / UI prefs (server-backed)

`GET/PUT /v1/settings/ui` + skins catalog:

- Theme, skin, locale
- Auto-follow, activity display
- Sidebar order
- Default model + default reasoning
- Auto-approve default
- Display name
- Core `agents_md` memory

`GET /v1/skins` — global skins (default/Gold, Ares, Poseidon, Sisyphus, Mono)

---

## 14. Persistence layers

| Store | Dev (`devdb`) | Prod (`localdb`/`server`) | Holds |
|---|---|---|---|
| **App DB** (SQLAlchemy async) | SQLite | Postgres `APP_DB_NAME` | Users, catalogs, skills, MCP, models, sessions meta, configs |
| **LangGraph checkpointer** | SQLite | **Separate** Postgres `LANGGRAPH_CHECKPOINT_DB` | Chat messages + run state |
| **Workspace files** | local dir | `/data` volume | Agent files |
| **Sandbox volumes** | — | Docker named volumes | Sandbox FS |

### Relational schema highlights

- **Accounts:** `users`, `password_resets`
- **Global catalogs:** `skins`, `global_providers`, `global_models`, `global_skills`, `global_mcps`, `skill_files`
- **Per-user:** `user_configs`, `user_models`, `user_skills`, `user_mcps`
- **Sessions:** title, model, reasoning, auto_approve, pinned, workspace_path, forked_from, meta
- **Secrets:** Fernet-encrypted JSON fields (`CREDENTIAL_ENCRYPTION_KEY`)
- **Alembic** migrations + SQL seed (`global_seed.sql`)

---

## 15. Security

- bcrypt + signed cookies / JWT
- Dev header ignored when `DEV_MODE=false`
- Tenant isolation on sessions, skills, MCP, models, workspace, memory
- `workspace_id_for` ownership check — no cross-user workspace resolution
- Fernet secrets at rest; expanded secrets only in process memory
- MCP describe never leaks expanded `${VAR}`
- HITL on dangerous tools
- Sandbox network isolation + least-privilege docker proxy
- Optional gateway API key

---

## 16. Observability (opt-in `observability` profile)

### Tracing

- Langfuse LangChain callback (preferred) with **per-user** + **per-session** attribution
- Or OTLP bridge fallback (LangSmith OTEL → collector)

### Metrics (Prometheus `/metrics`)

- HTTP count/latency by method/path/status (SSE-safe ASGI middleware)
- Runs: total, errors, latency, active gauge, tokens, HITL decisions
- LLM/tool call counts & latencies via `PrometheusCallbackHandler`
- Bounded label cardinality (no per-user metric labels)
- Grafana provisioning in compose stack

---

## 17. Full `/v1` API surface

| Area | Endpoints (summary) |
|---|---|
| **Health** | `/healthz`, `/health`, `/health/detailed`, `/v1/health` |
| **Auth** | signup, login, logout, me, available, forgot, reset, change-password |
| **Models** | list, config, save, discover, save-bulk, delete, test, xai-oauth start/poll |
| **MCP** | servers list, tools list, put, delete, patch/toggle |
| **Skills** | list, content, save, delete, toggle, files save/delete, import |
| **Memory** | get/write core; memories list/file CRUD/toggle |
| **Workspace** | tree, file, raw, download, save, mkdir, delete, rename, upload; `/v1/media` |
| **Settings** | UI get/put, skins |
| **Chat** | `/v1/chat/completions` (SSE) |
| **Runs** | create, events SSE, approval respond, cancel; `/v1/capabilities` |
| **Sessions** | list, create, messages, import, patch, delete |
| **Metrics** | `/metrics` (when enabled) |

---

## 18. Bundled extras

- **MCP servers:** `joyjoy_demo.py`, `workspace_fs/`
- **~73 global skills** seeded (Airtable, arxiv, ComfyUI, Codex, Claude Code, design tools, etc.)
- **4 global models** seeded (Azure: o4-mini, o3, gpt-5, gpt-4.1) with `${AZURE_OPENAI_API_KEY}`
- **8 provider schemas** for the Providers UI
- Docker multi-stage image (Node SPA build → Python runtime + uv/uvx + LibreOffice)
- Compose profiles: `devdb` / `localdb` / `server` + `sandbox` + `observability`

---

## 19. Stack

- Python ≥ 3.11, FastAPI, uvicorn, sse-starlette
- deepagents 0.6.11, langgraph ≥ 1.2, langchain-*
- SQLAlchemy 2.0 async, Alembic, SQLite / Postgres (psycopg)
- cryptography (Fernet), bcrypt, JWT/cookies
- Optional: OpenSandbox, Langfuse, Prometheus/Grafana, LibreOffice

### Source layout (`backend/app/`)

```
main.py        # app assembly + lifespan (env, DB, persistence, warm-up, SPA mount)
core/          # config, auth, context, constants, enums, observability, text/time utils
db/            # models, engine, crypto (Fernet), seed, seeds/*.sql
agent/         # agent.py (build+cache), prompts, middleware, runs (SSE+HITL), xai_oauth, agent_common
routes/        # auth, models, mcp, skills, memory, workspace, settings_ui, chat, runs, sessions, health
stores/        # sessions, users, usersettings, skills_store, mcp_runtime, memory_store,
               #   persistence (checkpointer/store), dbfs (DB→agent-FS bridge)
workspace/     # workspace files, media (/v1/media; office→PDF)
sandbox/       # OpenSandbox integration (opt-in code/shell execution)
```

Bundled MCP servers live in `backend/mcp_servers/` (`joyjoy_demo.py`, `workspace_fs/`).

---

## Configuration (common env)

| Var | Purpose |
|-----|---------|
| `DEV_MODE` | `true` = relaxed auth (`X-User-Id`); `false` = cookie/JWT only |
| `COMPOSE_PROFILES` | Infra switch: `localdb`/`devdb`/`server` + `sandbox` + `observability` |
| `DB_HOST` / `DB_PORT` / `DB_USERNAME` / `DB_PASSWORD` | Postgres (localdb/server) |
| `APP_DB_NAME` / `LANGGRAPH_CHECKPOINT_DB` | Separate Postgres DBs for app data vs checkpoints |
| `JWT_SECRET` | Session cookies / JWTs — required & stable when `DEV_MODE=false` |
| `CREDENTIAL_ENCRYPTION_KEY` | Fernet key — generate once; rotating orphans secrets |
| `AZURE_OPENAI_API_KEY` / `AZURE_OPENAI_ENDPOINT` | Seeded model creds (`${VAR}` refs) |
| `WORKSPACE_ROOT` | Agent workspace files root |
| `JOYJOY_INTERRUPT_TOOLS` | Extra built-ins to HITL-gate (MCP tools auto-gate) |
| `OPENSANDBOX_API_KEY` / `SANDBOX_*` | Sandbox connection (profile is on/off) |
| `OTEL_EXPORTER_OTLP_*` / `LANGFUSE_*` | Tracing transport (profile is on/off) |

---

## In one line

Joyjoy’s backend is a **multi-tenant Deep Agents platform**: FastAPI + LangGraph agent cache, SSE runs with HITL, multi-provider models (incl. xAI OAuth + live discovery), MCP/skills/memory CRUD, per-thread workspaces with optional sandboxed code exec, dual persistence (app DB + checkpointer), and opt-in observability — all behind one process that also serves the SPA.

---

*Generated from backend source inspection (`backend/app`, `backend/README.md`, `ARCHITECTURE.md`, DB models/seed, and key agent/route modules).*
