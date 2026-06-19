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
  • agent.py       one compiled create_deep_agent(); Azure OpenAI model
  • context.py     AgentContext(user_id, thread_id) → store namespace (user_id,"fs")
  • persistence.py dev: AsyncSqliteSaver + FilesystemBackend(local, per-user dir)
  │               prod: AsyncPostgresSaver + StoreBackend(AsyncPostgresStore, ns=(user_id,…))
  ▼
Azure OpenAI (o4-mini / o3 / gpt-5)        + LangSmith traces (optional, per user)
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
- `POST /v1/runs` + `GET /v1/runs/{id}/events` — SSE with tool-progress + `approval.request` (phase 2)

## 7. Required hermes-webui patches (all in `webui/`)
1. **Config only** (no code): `HERMES_WEBUI_CHAT_BACKEND=gateway`,
   `HERMES_WEBUI_GATEWAY_BASE_URL=http://localhost:8080`,
   `HERMES_WEBUI_GATEWAY_API_KEY=<GATEWAY_API_KEY>`,
   (phase 2) `HERMES_WEBUI_GATEWAY_USE_RUNS_API=true`.
2. **Forward user identity** → add `X-User-Id` header on the gateway request (true multi-tenant isolation).
3. **Forward session id** → `X-Thread-Id` so deepagents thread == hermes session.
4. **Skills/MCP panels** → point "global (read-only) + user" management at backend endpoints (phase 3).

## 8. Phased checklist
- [x] **Phase 0 — scaffold**: project, `.env`, persistence factory, agent factory, `/healthz`, `/v1/chat/completions`, dev SQLite smoke test — **DONE & validated live** (streaming SSE, cross-thread persistence, tenant isolation, Azure o4-mini)
- [x] **Phase 1 — wire UI — DONE & validated in-browser (headed + headless)**. 1b multi-user accounts live: `alice`/`bob` log in by username+password; alice's chat (Azure o4-mini) wrote a file → bob's agent read it → **NOFILE** (per-user backend isolation proven). Headed via chrome-devtools MCP; headless via Chrome CDP (login `{ok:true}`, `logged_in:true`). Evidence: `tst/joyjoy-{alice-chat,bob-isolated,headless-login,headless-app}.png`.
  - Follow-ups: (a) add a gateway **heartbeat endpoint** so the cosmetic "Gateway heartbeat failed" banner clears (chat works regardless); (b) the webui **conversation sidebar is instance-global** (bob sees alice's conversation *titles*) — partition the webui session store per user if per-user conversation lists are required (separate from 1b's backend isolation).
- [ ] **Phase 2 — runs API**: `/v1/runs` + events (tool progress + approvals); user/thread forwarding
- [ ] **Phase 3 — skills + MCP**: global (RO) + user endpoints + UI panels
- [ ] **Phase 4 — credentials**: encrypted `credentials` table replacing `auth.json`; per-user provider keys
- [ ] **Phase 5 — prod**: `APP_ENV=prod` (Postgres store+saver), run `.setup()` migrations, load test, sandbox `execute`
- [ ] **Phase 6 — ops**: docker-compose (backend + webui + postgres), CI

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
