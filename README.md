<p align="center">
  <img src="docs/branding/png/joyjoy-primary.png" alt="joyjoy" width="380">
</p>

# joyjoy

Multi-tenant **Deep Agents** assistant: a **single FastAPI process** that serves both
the **React SPA** and the `/v1` API to many users, with **all application data in one
relational database**.

- **One process, many users** — per-user isolation via the authenticated identity (`User.id`) + LangGraph thread ids.
- **Dev = SQLite, Prod = Postgres** — flip with the `APP_ENV` env var; *same code*, the DB URL is derived from it.
- **No file-based CRUD stores** — accounts, skins, providers, models, MCP servers, skills, sessions, and per-user config/memory all live in the DB. Chat *messages* stay in LangGraph's checkpointer. Provider secrets are **Fernet-encrypted at rest**.
- **React SPA** (Vite + React 19 + TypeScript, assistant-ui, Tailwind v4, shadcn, TanStack Query, i18n) is built to `frontend/dist` and served by the backend — no separate UI server.
- **Sandboxed execution (optional)** — when `SANDBOX_ENABLED=true`, the agent's file CRUD + code/shell runs inside a per-`(user, thread)` **OpenSandbox** container (durable Docker volume per chat) instead of the host. The bundled `joyjoy/sandbox-fat` image is multi-language: **Python, Node.js, Java (JDK 17), Go, Rust, C/C++** + Playwright/browsers + data/media/doc tooling (pandas, ffmpeg, LibreOffice, …).

See **[docs/RUNNING.md](./docs/RUNNING.md)** for dev/prod run modes + the data
architecture, **[PLAN.md](./PLAN.md)** for the architecture & checklist, and
**[CLAUDE.md](./CLAUDE.md)** for contributor details.

## Layout
- `backend/` — FastAPI + deepagents engine; `app/db/` (13 SQLAlchemy models, async engine, Fernet, seeds), `app/dbfs.py` (DB→agent backend bridge), `alembic/` (migrations)
- `frontend/` — the React SPA (built to `frontend/dist`, served by the backend) — see [frontend/README.md](./frontend/README.md)
- `backend/app/db/seeds/global_seed.sql` — the **single** seed for all shipped/global data (skins, providers, base models, MCP, skills + files); loaded into an empty DB on first boot. No `config/`, no skills tree — global data lives entirely in the DB. Model keys are `${AZURE_OPENAI_API_KEY}` env-refs in the SQL (real key in `.env`).
- `sandbox-image/` — Dockerfile for the multi-language `joyjoy/sandbox-fat` execution image (built automatically by `start_all.sh` if missing)
- `scripts/` — `start_all.sh` (one-command full stack), `serve.sh` (build SPA + run backend), `restart_backend.sh`
- `data/` — dev SQLite DBs + per-user workspace files (gitignored)
- `docs/branding/` — brand kit: logos, favicons, brand guide

## Run on any machine (dev)

**Prerequisites (install once):** [Docker](https://docs.docker.com/engine/install/) (running), [`uv`](https://docs.astral.sh/uv/), and Node 22 (e.g. via [`nvm`](https://github.com/nvm-sh/nvm)). On Windows, run everything inside WSL2.

```bash
git clone <repo> joyjoy && cd joyjoy
cp .env.example .env        # then fill keys: a model API key, OPENSANDBOX_API_KEY,
                            # JWT_SECRET, CREDENTIAL_ENCRYPTION_KEY
bash scripts/start_all.sh   # → open http://localhost:8080  (sign up, then log in)
```

`start_all.sh` is **idempotent and self-bootstrapping** — on first run it `uv sync`s the
backend, `npm install`s the frontend, builds the multi-language sandbox image, builds
the SPA, then starts everything (re-runs skip what's already done):

| Service | Port | Notes |
|---|---|---|
| Backend (SPA + `/v1` API) | `:8080` | one FastAPI process; the **FE has no separate server** |
| OpenSandbox server | `:8090` | code/shell execution layer (needs Docker; gated by `SANDBOX_ENABLED`) |
| jira MCP (mcp-atlassian) | `:9000` | optional — skipped unless `JIRA_MCP_DIR` exists |

The only things the script can't do for you are the **system prerequisites** above and
the **`.env`** secrets. Paths are derived at runtime, so the repo can live anywhere.

**Other scripts:** `scripts/serve.sh` rebuilds the SPA and restarts only the backend (no
sandbox/jira); `scripts/restart_backend.sh` restarts the backend to pick up `app/` changes.
To iterate on the UI with hot-reload: `cd frontend && npm run dev` (Vite on `:5173`, proxies the API).

> Sandbox is optional: leave `SANDBOX_ENABLED` unset/false for a pure SQLite dev run
> with **zero external services** — the agent then uses the host filesystem instead of
> a container (no Docker/OpenSandbox needed).

On first boot the backend creates the tables and seeds the shipped catalogs
(skins, providers, base models, global MCP servers, 73 global skills). When not
signed in, dev falls back to a seeded **dev user** so the agent works without login.

**Models** are managed in the UI under **Settings → Providers** (Azure OpenAI,
Azure AI Foundry/Claude, Bedrock, OpenAI-compatible, Gemini) — keys are
Fernet-encrypted at rest and masked in the UI. **Skills**, **MCP**, and **Memory**
have their own tabs (global = read-only; per-user = full CRUD).

## Prod (Postgres)
Set `APP_ENV=prod` + `DATABASE_URL=postgresql://…` (and `CREDENTIAL_ENCRYPTION_KEY`,
`JWT_SECRET` — generated on first boot if blank). The app DB and the LangGraph
checkpointer share one Postgres database via disjoint tables. Details in
[docs/RUNNING.md](./docs/RUNNING.md).

**Containerized (Postgres + app, no sandbox):** the repo ships a `docker-compose.yml`.
Set `JWT_SECRET`, `CREDENTIAL_ENCRYPTION_KEY`, and `AZURE_OPENAI_API_KEY` in `.env`, then:
```bash
docker compose up --build      # → http://localhost:8080
```
This brings up Postgres + the app (schema + seed auto-load on first boot). It does **not**
include the OpenSandbox execution layer — use `scripts/start_all.sh` for that.
