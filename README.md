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
- **Bring your models** — Azure OpenAI, Anthropic (incl. Azure AI Foundry `/anthropic`), AWS Bedrock, Google GenAI, NVIDIA NIM, or any OpenAI-compatible endpoint (OpenRouter, DeepSeek, Groq, local servers, …); global catalog + per-user additions. Add a model by **fetching the provider's live catalog** and picking from it (or type an id by hand) — no need to know exact model names in advance.
- **Skills & MCP tools** — global (read-only) + per-user, managed from the UI; all MCP/plugin tool calls auto-gate for human approval (HITL).
- **Per-user memory & workspace** — durable `AGENTS.md` memory and a real per-thread file workspace (downloadable, inline media previews).
- **Generative UI** — agents can emit rich UI: `render_ui` (JSON component kit) and `render_html` (sandboxed HTML canvas), toggleable per session.
- **Opt-in sandbox** — per-session isolated containers for code/shell execution.

## Quick start (Docker)

```bash
# 1. cp .env.example .env, then set the required secrets:
#    JWT_SECRET, CREDENTIAL_ENCRYPTION_KEY  (generate once, keep stable)
#    AZURE_OPENAI_API_KEY                   (base model key)
#    COMPOSE_PROFILES                       (defaults to `devdb` = zero-dep SQLite)
# 2. build + run
docker compose up --build
# 3. open http://localhost:8080  → sign up / log in
```

On first boot the app creates the schema and seeds the global catalogs (skins, providers, models, skills, MCP) from `backend/app/db/seeds/global_seed.sql`. No secret is stored in the seed — model keys are `${VAR}` refs resolved at runtime.

Everything the container writes (the `devdb` SQLite files, agent workspace files) lives on the `workspaces` volume, mounted at `CONTAINER_DATA_DIR` (default `/data`) — so signups, added models, and chats all survive a `docker compose up --build` rebuild, not just a plain restart.

**`COMPOSE_PROFILES` is the single switch** — the backend self-configures its DB, sandbox, and observability from it (no separate `SANDBOX_ENABLED`/`METRICS_ENABLED`/`TRACING_ENABLED` flags). Pick a DB backend and add opt-in tiers:
- `devdb` — no external DB; local SQLite (app DB + LangGraph checkpointer). Zero deps.
- `localdb` — bundled Postgres 16 (creates two databases: app + LangGraph checkpoints).
- *(neither)* — external Postgres from the `DB_*` vars in `.env` ("server" mode).
- `sandbox` — the code-execution tier. See [`ARCHITECTURE.md`](./ARCHITECTURE.md) §6.
- `observability` — Langfuse tracing + Prometheus/Grafana metrics.

```bash
COMPOSE_PROFILES=localdb,sandbox,observability docker compose up --build   # bash / WSL
```

## Quick start (local dev)

Set `DEV_MODE=true` in `.env`. With `COMPOSE_PROFILES=devdb` you need no containers at all:

```bash
# backend  (SQLite + no-auth dev user)
cd backend && uv pip install -e . && uvicorn app.main:app --port 8080 --reload

# frontend (Vite on :5173, proxies /v1 → :8080 as user "alice")
cd frontend && npm install && npm run dev
```

Need the bundled infra (Postgres / sandbox / Langfuse+Grafana) while still running the
backend on the host? Bring up **infra only** with the dev compose file, then run the app
yourself:

```bash
docker compose -f docker-compose.dev.yml up -d      # or: scripts/dev-up.sh  (picks the
                                                    # file from DEV_MODE in .env)
```

Or bring up the whole dev stack in WSL with `scripts/start_all.sh` (jira MCP → backend → SPA, idempotent).

## Repository layout

```
backend/    FastAPI + deepagents + LangGraph   → see backend/README.md
frontend/   React 19 + Vite SPA (assistant-ui) → see frontend/README.md
scripts/    start_all.sh, run_atlassian_wsl.sh, install_{bedrock,gemini}.sh, run-backend.sh …
docs/       branding + notes
Dockerfile            multi-stage: build SPA → run backend (serves both)
docker-compose.yml    baked stack (SPA+backend in one image) + profile-gated infra
docker-compose.dev.yml  infra only (no backend) — for running the backend on the host
sandbox.toml          OpenSandbox server config (runtime/egress/network hardening)
ARCHITECTURE.md       full architecture (data flow, security, deployment)
```

## Documentation

- **[ARCHITECTURE.md](./ARCHITECTURE.md)** — system design: components, data stores, integrations, deployment, security, roadmap.
- **[backend/README.md](./backend/README.md)** — backend dev guide (run, config, API surface, key concepts).
- **[frontend/README.md](./frontend/README.md)** — frontend dev guide (run, build, runtime, generative UI).
