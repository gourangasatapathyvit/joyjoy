# Running joyjoy — dev vs prod, and where data lives

joyjoy keeps **all application data in one relational database** (accounts, skins,
providers, models, MCP servers, skills, sessions, per-user config + memory).
Chat *messages* stay in LangGraph's checkpointer. There are **no JSON/file-based
config stores** for CRUD data anymore — everything is read/written through the DB.

The single switch is the **`APP_ENV`** env var:

| `APP_ENV` | App DB (this schema)            | LangGraph checkpointer/store |
|-----------|---------------------------------|------------------------------|
| `dev` (default) | **SQLite** file `APP_DB_PATH` (`data/joyjoy.db`) via aiosqlite | SQLite (`data/*.sqlite`) |
| `prod`    | **Postgres** from `DATABASE_URL` (psycopg async) | Postgres (same DB) |

`Settings.app_db_url` derives the SQLAlchemy URL from `APP_ENV`:
dev → `sqlite+aiosqlite:///<abs APP_DB_PATH>`; prod → `DATABASE_URL` rewritten to
`postgresql+psycopg://…`. On startup the app ensures all tables exist
(`create_all`) and seeds the shipped catalogs (skins, providers, base models, the
global MCP servers, the 73 global skills) idempotently.

## Secrets at rest

- **Model provider secrets** (`api_key`, AWS secret/session tokens) are
  **Fernet-encrypted** before they touch the DB and decrypted only when a chat
  model is built. The key is `CREDENTIAL_ENCRYPTION_KEY`.
- `JWT_SECRET` signs the session cookie; passwords are bcrypt-hashed.
- Both `CREDENTIAL_ENCRYPTION_KEY` and `JWT_SECRET` are **generate-once**: if
  unset on first boot the app mints one and writes it to `.env`. **Do not rotate
  `CREDENTIAL_ENCRYPTION_KEY`** after secrets are stored — it would orphan them.
- MCP server secrets are NOT stored in the DB: use `${VAR}` references in the
  server's `env`/`headers` (the real value lives in `.env` / the process env and
  is expanded only when the connection is built). `describe_mcp` never returns
  `env`/`headers`.

## Run — dev (SQLite, no external DB)

```bash
# .env: APP_ENV=dev  (APP_DB_PATH defaults to ./data/joyjoy.db)
cd backend
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8080
```

The backend serves the built React SPA (`frontend/dist`) at `/`, so this single
process is the whole app. Rebuild the SPA with `cd frontend && npm run build`.

When not signed in, dev requests fall back to a seeded **dev user** so the agent
and workspace work without logging in. Sign-up/login create real accounts.

## Run — prod (Postgres)

```bash
# .env:
#   APP_ENV=prod
#   DATABASE_URL=postgresql://user:pass@host:5432/joyjoy_db   (@ in pwd → %40)
#   CREDENTIAL_ENCRYPTION_KEY=...   (generated on first boot if blank)
#   JWT_SECRET=...
cd backend
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8080
```

The app DB and the LangGraph checkpointer share the one Postgres database
(`joyjoy_db`) but use disjoint tables, so they don't collide.

## Workspace files

Agent working files stay on disk under `WORKSPACE_ROOT/<uid>/workspace/<workspace_id>`
(`WORKSPACE_ROOT` defaults to `USER_DATA_ROOT`). Each `session` row stores a
**relative** `workspace_path`; the root is resolved from config, so the volume can
be repointed (shared mount / object-storage backend) without touching the DB.

## Schema / migrations

Models live in `app/db/models.py` (13 tables). Fresh databases are bootstrapped by
`create_all` on startup — no migration step needed to start. Schema **changes**
are managed with Alembic:

```bash
cd backend
.venv/bin/alembic revision --autogenerate -m "describe change"
.venv/bin/alembic upgrade head
```

## Seed data (global / non-user)

ALL shipped/global data — skins, providers, base models, MCP servers, and the
global skills + their files — lives in **one committed SQL file**,
`backend/app/db/seeds/global_seed.sql` (plain INSERTs, no user data). On first boot,
if the DB is empty, the app loads it automatically (`seed.seed_all`); it's a no-op
once the DB is populated. There is no `config/` dir, no skills bundle, and no seed
constants — the SQL is the single source of global data; the DB is authoritative at
runtime.

**Model API keys** are NOT in the SQL: each model's `api_key` is the literal env-ref
`${AZURE_OPENAI_API_KEY}`. The real key lives in `.env` (gitignored) and is expanded
at runtime — so no secret is ever committed. Set `AZURE_OPENAI_API_KEY` in `.env`.

To change global data: load the seed, edit the rows in the DB (or the UI), then
regenerate the file with `scripts/dump_global_seed_sql.py` (keeps `${VAR}` env-refs;
blanks any real secrets). You can also load it manually into a fresh DB:

```bash
psql "$DATABASE_URL" -f backend/app/db/seeds/global_seed.sql     # prod (Postgres)
sqlite3 data/joyjoy.db < backend/app/db/seeds/global_seed.sql    # dev (SQLite)
```
