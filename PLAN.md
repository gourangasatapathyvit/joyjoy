# joyjoy — Multi-Tenant Deep Agents behind hermes-webui

A **single FastAPI process** serving **many users** on one Deep Agents engine, with
**all state in Postgres** (prod) or **SQLite + local files** (dev). `hermes-webui`
is the chat UI, talking to the backend over its existing **"gateway"** contract.

> This file is the living plan + checklist. Update the checkboxes as we go.

## 1. Goal & hard constraints
- **Single process, many users** — no per-user subprocess. `asyncio` concurrency.
- **Production multi-tenant; everything in Postgres** so a pod can die with **zero data loss**:
  threads/checkpoints, conversation history, provider credentials, long-term memory, skills, virtual filesystem.
- **Dev/prod parity** — dev = SQLite + local files; prod = Postgres. *Same agent code*; persistence swapped via a factory keyed on `APP_ENV`.
- **Reuse hermes-webui UX** — patch only what is required.

## 2. Architecture (mirrors `deepagent/flow.txt`)
```
Browser
  │  (hermes login: cookie/JWT)
  ▼
hermes-webui  (auth, sessions, chat UI)   webui/   CHAT_BACKEND=gateway
  │  HTTP gateway contract
  │    POST /v1/chat/completions            (OpenAI SSE)        ← MVP
  │    POST /v1/runs + GET /v1/runs/{id}/events (SSE)           ← tools + HITL approvals (phase 2)
  │    headers: X-API-Key, X-User-Id, X-Thread-Id
  ▼
joyjoy-backend  (FastAPI, ONE process)     backend/app/
  • auth.py        gateway key + per-user identity (X-User-Id / JWT sub)
  • agent.py       create_deep_agent() cached per (kind,user,model); multi-provider build_model_for()
  • context.py     AgentContext(user_id, thread_id) → store namespace (user_id,"fs")
  • persistence.py dev: AsyncSqliteSaver + FilesystemBackend(local, per-user dir)
  │               prod: AsyncPostgresSaver + StoreBackend(AsyncPostgresStore, ns=(user_id,…))
  ▼
Model providers (build_model_for): Azure OpenAI · Azure AI Foundry/Claude · Bedrock · OpenAI-compat · Gemini
  ▼
Postgres `langgraph_db` (10.44.63.72)  — checkpoints + store(memory, skills, virtual FS) + creds table
```

## 3. "Everything in Postgres" mapping (replaces the dcode local files)
| dcode local file | joyjoy **prod** | joyjoy **dev** |
|---|---|---|
| `~/.deepagents/.state/sessions.db` (threads) | `AsyncPostgresSaver` (langgraph_db) | `AsyncSqliteSaver` (`./data/dev_checkpoints.sqlite`) |
| `history.jsonl` (input history) | thread messages in the checkpointer | same (sqlite) |
| `auth.json` (provider creds) | encrypted `credentials` table (Fernet) | `.env` / local |
| `agent/skills/`, `AGENTS.md` (memory), virtual FS | `AsyncPostgresStore` namespaces per user | `FilesystemBackend` local dirs |

## 4. Multi-tenant isolation model
- `user_id` resolved from `X-User-Id` (hermes forwards the authenticated user) or JWT `sub` (direct clients per flow.txt).
- Per-request `AgentContext(user_id, thread_id)` → `StoreBackend` namespace `(user_id, "fs")` for FS/memory; `(user_id, "skills")` for user skills.
- **Global** (shared, read-only) skills/MCP live under a fixed namespace `("global", …)` / mounted dir; never writable by users.
- `thread_id` = hermes session id (forwarded as `X-Thread-Id`) so the deepagents thread lines up with the UI sidebar.

## 5. Repo layout
```
joyjoy/
  backend/
    app/{config,persistence,context,auth,agent,main}.py
    pyproject.toml
  webui/                 patched copy of hermes-webui  (CHAT_BACKEND=gateway)
  skills/global/         read-only global skills (SKILL.md dirs)
  config/global.mcp.json global MCP servers (merged for every user)
  data/                  dev sqlite + per-user files  (gitignored)
  scripts/               run / db-init helpers
  docs/  PLAN.md  .env  .env.example
```

## 6. Gateway contract the backend implements (for hermes)
- `GET  /healthz`, `GET /v1/models`
- `POST /v1/chat/completions` — OpenAI-compatible **SSE** (default gateway path) — **MVP**
- `POST /v1/runs` + `GET /v1/runs/{id}/events` + `POST /v1/runs/{id}/approvals/{aid}/respond` — SSE with tool-progress + `approval.request`
- Per-user CRUD/config (all `X-User-Id`-scoped; global ids are read-only): `/v1/skills/*`, `/v1/mcp/servers/*`, `/v1/models/config*`, `/v1/memory*`

## 7. Required hermes-webui patches (all in `webui/`)
1. **Config only** (no code): `HERMES_WEBUI_CHAT_BACKEND=gateway`,
   `HERMES_WEBUI_GATEWAY_BASE_URL=http://localhost:8080`,
   `HERMES_WEBUI_GATEWAY_API_KEY=<GATEWAY_API_KEY>`,
   (phase 2) `HERMES_WEBUI_GATEWAY_USE_RUNS_API=true`.
2. **Forward user identity** → add `X-User-Id` header on the gateway request (true multi-tenant isolation).
3. **Forward session id** → `X-Thread-Id` so deepagents thread == hermes session.
4. **Skills/MCP panels** → point "global (read-only) + user" management at backend endpoints (phase 3).

## 8. Status / phased checklist
> Detailed, current architecture for contributors is in **[CLAUDE.md](./CLAUDE.md)**.

- [x] **Phase 0 — scaffold**: persistence factory, agent factory, `/healthz`, `/v1/chat/completions`, dev SQLite — **DONE & validated** (streaming SSE, cross-thread persistence, tenant isolation).
- [x] **Phase 1 — wire UI**: gateway mode; multi-user accounts (`alice`/`bob`) with per-user **backend** isolation proven; gateway **heartbeat** endpoint added; **per-user conversation sidebar** (session→owner map, `/api/sessions` filtered). **DONE & validated in-browser**.
- [x] **Phase 2 — runs API**: `/v1/runs` + `/v1/runs/{id}/events` (SSE) + `/respond` approvals + `/v1/capabilities`. HITL: every MCP/plugin tool is gated for approval in run mode. **DONE & validated** (live tool card → Allow once → resume).
- [x] **Phase 3 — skills + MCP**: global (read-only) + per-user, runtime-loaded (no recompile). Skills = disk `skills/global/` + per-user store; MCP = `config/global.mcp.json` + `data/users/<uid>/mcp.json` (langchain-mcp-adapters). **Full CRUD from the UI** (Skills / MCP / Memory tabs). 72 Hermes skills copied into global. Active MCP: `jira` (http), `web-search` (uvx duckduckgo), demo. **DONE & validated**.
- [x] **Models / providers** *(added beyond the original plan)*: store-backed catalog — global `config/models.json` + per-user `data/users/<uid>/models.json` — managed from **Settings → Providers** (CRUD; global read-only). Five provider types via `agent.build_model_for` dispatch: `azure_openai`, `anthropic` (Azure AI Foundry/Claude), `bedrock`, `openai` (OpenAI-compatible), `gemini`. Keys live in the gitignored JSON files, masked in the UI; chat picker grouped by provider. **DONE & validated**.
- [~] **Phase 4 — credentials**: per-user provider keys are handled via the Providers-tab catalog (plain **gitignored** JSON files). The encrypted `credentials` table (Fernet, `CREDENTIAL_ENCRYPTION_KEY`) is scaffolded for prod but is **not yet** the active store.
- [~] **Phase 5 — prod Postgres**: prod store+saver on isolated **`joyjoy_db`** proven (conn pool; write / cross-thread / isolation). Load test + sandboxed `execute` still pending.
- [ ] **Phase 6 — ops**: docker-compose (backend + webui + postgres), CI; pin provider SDKs (`langchain-anthropic` / `-aws` / `-google-genai`) into `pyproject.toml` (currently installed ad-hoc).

**Also done:** Hermes fully uninstalled — joyjoy is standalone (its own venvs for backend + webui); the UI was de-Hermes rebranded (user-facing strings → "joyjoy"; internal `hermes` / `HERMES_WEBUI_*` / `X-Hermes-*` identifiers deliberately kept — they are load-bearing).

## 8b. Runs queue & streaming — current design + agreed prod hardening (note)

**Current (single-process — correct for now):** `backend/app/runs.py` uses one in-process
`asyncio.Queue` per run (producer = a `_drive` task via `asyncio.create_task`; consumer =
the `/v1/runs/{id}/events` SSE generator), an in-memory `_RUNS` registry, and
`asyncio.Future`s for HITL approvals. This is the standard single-process SSE pattern —
confirmed in-house: the sibling app **`ai_sdlc_dashboard`** uses the same `asyncio.Queue`
+ `asyncio.create_task` model (no Celery/arq/taskiq, explicit `replicas: 1`), and it
matches how LangGraph Platform splits state.

**Known weak spots (NOT urgent; fine for dev/single-host):**
1. The runs queue is **unbounded** (no backpressure) — a chatty run with a disconnected client can grow memory.
2. `_RUNS` is **in-memory** — runs/approvals are lost on restart, and `_RUNS` cleanup relies on the client hitting `/events`.

**Agreed prod-hardening path — mirror `ai_sdlc_dashboard` (NOT a task broker, NOT multi-replica):**
- **Bound the queue:** `asyncio.Queue(maxsize=256)` + drop-oldest on overflow (exactly what `ai_sdlc_dashboard`'s `sse_manager.py` does).
- **Durable run state in Redis:** run records + paused snapshots (with TTL) so a pod restart can resume; keep durable agent state in **Postgres** (already done). Redis here is for durability + cross-process signaling (pub/sub), **not** cross-replica fan-out.
- **Stay single-pod** (`Recreate` deploy strategy). Don't add Celery/arq/taskiq unless run execution genuinely needs a distributed worker pool.
- **Heavier options only if ever needed:** adopt LangGraph Platform's `langgraph-api` (productized runs+streaming), or Redis Streams/NATS + an async task queue (arq / taskiq / Procrastinate-on-Postgres).

## 9. To verify on first run (scaffold is written defensively for these)
- langgraph `context=` kwarg on `ainvoke`/`astream` in 1.2.6 (else config-metadata fallback — the namespace factory already handles both).
- Azure `o4-mini` tool-calling through deepagents.
- `StoreBackend` namespace receives `AgentContext.user_id`.
- `AsyncPostgresSaver` / `AsyncPostgresStore` `.setup()` against `langgraph_db`.

## 10. Dev run (after scaffold)
```bash
cd ~/joyjoy/backend
uv venv && source .venv/bin/activate
uv pip install -e .
# APP_ENV=dev by default → SQLite + local files
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
# smoke test:
curl -s localhost:8080/healthz
```
