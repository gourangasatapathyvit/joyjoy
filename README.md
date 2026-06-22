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

See **[docs/RUNNING.md](./docs/RUNNING.md)** for dev/prod run modes + the data
architecture, **[PLAN.md](./PLAN.md)** for the architecture & checklist, and
**[CLAUDE.md](./CLAUDE.md)** for contributor details.

## Layout
- `backend/` — FastAPI + deepagents engine; `app/db/` (13 SQLAlchemy models, async engine, Fernet, seeds), `app/dbfs.py` (DB→agent backend bridge), `alembic/` (migrations)
- `frontend/` — the React SPA (built to `frontend/dist`, served by the backend) — see [frontend/README.md](./frontend/README.md)
- `config/global.mcp.json`, `config/models.json` — global MCP/model seed sources (seeded into the DB on first boot). Global skills ship as a committed DB seed bundle (`backend/app/db/seeds/global_skills.json`) — there is no loose skills/ tree; global skills live entirely in the DB.
- `data/` — dev SQLite DBs + per-user workspace files (gitignored)
- `docs/branding/` — brand kit: logos, favicons, brand guide

## Quick start (dev — SQLite, zero external deps)

**Build the SPA and serve everything from one process** (`:8080`):
```bash
bash ~/joyjoy/scripts/serve.sh          # builds frontend/ then starts the backend
# open http://127.0.0.1:8080  → sign up, then log in
```

Or run the pieces by hand:
```bash
# backend (APP_ENV=dev → SQLite at data/joyjoy.db; serves the prebuilt SPA + /v1)
cd ~/joyjoy/backend
uv venv && uv pip install -e .          # first time (uv-managed venv)
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8080
curl -s 127.0.0.1:8080/v1/health

# frontend (only when iterating on UI; Vite dev server with API proxy)
cd ~/joyjoy/frontend && npm install && npm run dev      # :5173
# or just rebuild the bundle the backend serves:  npm run build
```

**Whole stack** (jira MCP `:9000` → backend `:8080`, idempotent):
`bash ~/joyjoy/scripts/start_all.sh` (build the SPA first if it's stale).

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
