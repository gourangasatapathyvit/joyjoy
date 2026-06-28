<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/branding/svg/joyjoy-dark.svg">
    <img src="docs/branding/png/joyjoy-primary.png" alt="joyjoy" width="280">
  </picture>
</p>

# joyjoy

A multi-tenant **Deep Agents** platform. A single **FastAPI** process serves a **React SPA** and a **`/v1` JSON/SSE API** on one port (`:8080`). Each user gets a private, isolated agent workspace, long-term memory, skills, and MCP tools, with optional human-in-the-loop approvals and an opt-in code-execution sandbox.

```
React 19 SPA  ──HTTPS (cookie auth)──►  FastAPI  ──►  deepagents + LangGraph
(assistant-ui)   POST /v1/runs (SSE)     (:8080)       │
                                                       ├─ app DB (SQLite dev / Postgres prod)
                                                       ├─ LangGraph checkpointer (chat history)
                                                       ├─ per-user workspace files
                                                       └─ model providers · MCP servers · sandbox
```

## What it does

- **Multi-tenant agents** — one compiled agent per `(user, model, reasoning, genui)`, cached in-process; per-request `user_id` + `thread_id` isolation.
- **Bring your models** — Azure OpenAI, Anthropic (incl. Azure AI Foundry `/anthropic`), AWS Bedrock, Google GenAI; global catalog + per-user additions.
- **Skills & MCP tools** — global (read-only) + per-user, managed from the UI; all MCP/plugin tool calls auto-gate for human approval (HITL).
- **Per-user memory & workspace** — durable `AGENTS.md` memory and a real per-thread file workspace (downloadable, inline media previews).
- **Generative UI** — agents can emit rich UI: `render_ui` (JSON component kit) and `render_html` (sandboxed HTML canvas), toggleable per session.
- **Opt-in sandbox** — per-session isolated containers for code/shell execution.

## Quick start (Docker)

```bash
# 1. set required secrets in .env (compose reads it):
#    JWT_SECRET, CREDENTIAL_ENCRYPTION_KEY  (generate once, keep stable)
#    AZURE_OPENAI_API_KEY                   (base model key)
#    DATABASE_URL                           (prod Postgres) — or use the localdb profile below
# 2. build + run
docker compose up --build
# 3. open http://localhost:8080  → sign up / log in
```

On first boot the app creates the schema and seeds the global catalogs (skins, providers, models, skills, MCP) from `backend/app/db/seeds/global_seed.sql`. No secret is stored in the seed — model keys are `${VAR}` refs resolved at runtime.

**Optional compose profiles** (independent; combine via `COMPOSE_PROFILES=sandbox,localdb`):
- `localdb` — bundled Postgres 16 for local dev (otherwise point `DATABASE_URL` at a hosted DB).
- `sandbox` — the code-execution tier (also set `SANDBOX_ENABLED=true`). See [`ARCHITECTURE.md`](./ARCHITECTURE.md) §6.

```bash
COMPOSE_PROFILES=sandbox,localdb docker compose up --build   # bash / WSL
```

## Quick start (local dev)

```bash
# backend  (SQLite + no-auth dev user)
cd backend && uv pip install -e . && uvicorn app.main:app --port 8080 --reload

# frontend (Vite on :5173, proxies /v1 → :8080 as user "alice")
cd frontend && npm install && npm run dev
```

Or bring up the whole dev stack in WSL with `scripts/start_all.sh` (jira MCP → backend → SPA, idempotent).

## Repository layout

```
backend/    FastAPI + deepagents + LangGraph   → see backend/README.md
frontend/   React 19 + Vite SPA (assistant-ui) → see frontend/README.md
scripts/    start_all.sh, run_atlassian_wsl.sh, install_{bedrock,gemini}.sh, run-backend.sh …
docs/       branding + notes
Dockerfile            multi-stage: build SPA → run backend (serves both)
docker-compose.yml    backend + optional localdb / sandbox profiles
sandbox.toml          OpenSandbox server config (runtime/egress/network hardening)
ARCHITECTURE.md       full architecture (data flow, security, deployment)
```

## Documentation

- **[ARCHITECTURE.md](./ARCHITECTURE.md)** — system design: components, data stores, integrations, deployment, security, roadmap.
- **[backend/README.md](./backend/README.md)** — backend dev guide (run, config, API surface, key concepts).
- **[frontend/README.md](./frontend/README.md)** — frontend dev guide (run, build, runtime, generative UI).
