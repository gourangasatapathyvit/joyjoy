# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

joyjoy is a single-process, multi-tenant **Deep Agents** app: a FastAPI + LangGraph backend (`backend/`) that **also serves the React SPA** (`frontend/`, built to `frontend/dist`, mounted via `app.frontend()`) — one process, one origin. One `create_deep_agent()` serves all users; per-user isolation is by the authenticated identity **`User.id` (uuid)** + `thread_id`. **All application data lives in one relational DB** (dev SQLite / prod Postgres, selected by `APP_ENV`); chat messages stay in the LangGraph checkpointer; provider secrets are Fernet-encrypted at rest. Optionally, the agent's file CRUD + code execution runs inside a per-`(user, thread)` **OpenSandbox** container (gated by `SANDBOX_ENABLED`). The legacy hermes-webui has been **removed**. See `README.md`, `PLAN.md`, `docs/RUNNING.md`.

## Environment: this project lives in WSL

The repo is at `~/joyjoy` inside **WSL Ubuntu**; you may be launched from Windows. This matters:

- Run all project commands through WSL: `wsl bash -lc "bash ~/joyjoy/scripts/<x>.sh"`. The **Bash tool is Git Bash** (Windows) and mangles `/home/...` paths — don't run project shell logic in it directly.
- Edit WSL files via the UNC path `\\wsl.localhost\Ubuntu\home\gourangasatapathy\joyjoy\...`.
- PowerShell→WSL quoting breaks on parens / `$` / nested quotes. For anything non-trivial, **write a `.sh`/`.py` file and run it** with `wsl bash /abs/path` rather than passing a complex inline command.
- WSL↔Windows are separate network namespaces: a service on the **Windows host is NOT reachable** from the WSL backend (Hyper-V firewall). Run dependencies (jira MCP, etc.) **inside WSL** on `127.0.0.1`.

## Running the stack

- **One command, whole stack:** `bash ~/joyjoy/scripts/start_all.sh`. Idempotent + **self-bootstrapping** — on first run it `uv sync`s the backend, `npm install`s the frontend, builds the sandbox image if missing, builds the SPA, then starts: OpenSandbox server `:8090`, jira MCP `:9000` (skipped unless `JIRA_MCP_DIR` exists), backend `:8080` (serves SPA + `/v1`). Re-runs skip whatever's already up. Scripts derive their repo root at runtime (no hardcoded paths).
- **Build SPA + restart backend only:** `scripts/serve.sh` (no sandbox/jira). **Restart backend after `app/` edits:** `scripts/restart_backend.sh`. **UI hot-reload:** `cd frontend && npm run dev` (Vite `:5173`, proxies `/v1` → `:8080`).
- ⚠️ `start_all.sh` does **not** restart an already-running `:8080`, so a fresh SPA build isn't picked up — use `serve.sh` / `restart_backend.sh` to force.
- The backend reads `~/joyjoy/.env` via pydantic `env_file="../.env"`, so it **must start from `backend/`** (the scripts handle this).
- UI: http://127.0.0.1:8080 — sign up / log in (`users` table). Dev falls back to a seeded dev user when not signed in.

## venvs are uv-managed — there is no `pip`

`backend/.venv` is created by **uv** (`cd backend && uv sync`; dev extras: `uv sync --extra dev`) and has **no `pip` binary**. To add a package ad-hoc: `cd ~/joyjoy/backend && VIRTUAL_ENV="$PWD/.venv" ~/.local/bin/uv pip install <pkg>` (from a script file, not inline). Deps are in `backend/pyproject.toml`, **but several are installed ad-hoc and NOT in pyproject**: the provider SDKs `langchain-anthropic`, `langchain-aws`+`boto3`, `langchain-google-genai`, and the **`opensandbox` SDK** — re-install them (and re-run `scripts/install_bedrock.sh` / `install_gemini.sh`) if the venv is rebuilt. Frontend is plain npm.

## Lint / tests

- Lint: `ruff` (dev extra; default config).
- pytest/pytest-asyncio are dev extras but there is **no substantive backend test suite** yet. `scripts/validate_models.py` is the main standalone check (parses every model spec + resolves `${VAR}` keys). Validate behavior against the live `/v1` API with a real session cookie.
- **Never `import app.main` from a standalone script** — it opens a DB connection at import and hangs. Parse `.env` into `os.environ` yourself (see `validate_models.py`).

## Architecture

### Frontend ↔ backend (same-origin)

The SPA calls `/v1/*` same-origin with `credentials: "include"`. Identity = an **httpOnly session cookie** whose `sub` is `User.id` (set by `/v1/auth/*`); `resolve_user_id` also accepts an `X-User-Id` header / bearer JWT and, in dev, falls back to a seeded dev user. Chat flows through `/v1/runs` + `/v1/runs/{id}/events` (SSE runs API with **HITL tool approvals**) or `/v1/chat/completions` (plain SSE). Endpoints are split under `backend/app/routes/`; the SPA build is mounted last via `app.frontend()`.

### Backend (`backend/app/`)

- `db/` — relational layer: `models.py` (13 SQLAlchemy tables), `engine.py` (async engine + `db_session()`; SQLite `PRAGMA foreign_keys=ON`), `crypto.py` (Fernet), `seeds/global_seed.sql` (single committed seed). **Adding a column:** SQLite `create_all` won't ALTER an existing table — for dev either wipe `data/joyjoy.db*` or `ALTER TABLE … ADD COLUMN`; prod needs an Alembic migration.
- `dbfs.py` — the **DB→agent bridge**: `MemoryBackend` + `DbSkillsBackend` (serves `/skills/user/` with `user_id=uid` and `/skills/global/` with `user_id=None`) — deepagents backends in `build_backend`'s `CompositeBackend`; async DB I/O, no disk. Binary helper files live in `skill_files` (base64).
- `agent.py` — the core (largest file). `_get_or_build()` compiles one `create_deep_agent()` per `(kind, user_id, model_id, reasoning)` and caches it (`_AGENT_CACHE`, bounded); **`_invalidate_user_cache(uid)` on every write**. `build_model_for` / `resolve_model` / `merged_model_specs` and the model·MCP·skill CRUD are **async** (read the DB, decrypt via `db.crypto`). `describe_providers()` reads the `global_providers` table (the provider field-schemas — no hardcoded `PROVIDER_TYPES`). `build_backend()` picks the sandbox vs host filesystem backend. MCP loading + per-run approval gating live here. Prompts are in `prompts.py` (triple-quoted); shared constants in `constants.py` (incl. `DEFAULT_USER_ID`).
- `routes/` — `runs.py`-backed run engine, `sessions.py`, `workspace.py` (dock + media), auth, etc. `users.py` accounts + OTP; `usersettings.py` UI prefs ↔ `user_configs`; `sessions.py` the `sessions` table; `config.py` `Settings`; `persistence.py` LangGraph saver+store (pinned `deepagents==0.6.10`).

### Capabilities = global (read-only) + per-user (CRUD) — one pattern, in the DB

Skills, MCP servers, the model catalog, and memory share one shape:

- **Global** = shipped read-only catalogs, ALL seeded from `backend/app/db/seeds/global_seed.sql` (skins, `global_providers`, `global_models`, `global_mcps`, `global_skills`+`skill_files`) — loaded into an empty DB on first boot (idempotent). Model `api_key`s are `${AZURE_OPENAI_API_KEY}` env-refs in the SQL (no secret committed). Regenerate from a populated DB with `scripts/dump_global_seed_sql.py`.
- **Per-user** = writable rows keyed by `User.id`: `user_models`, `user_mcps`, `user_skills`(+`skill_files`), `user_configs`. Writes to a **global** id are rejected as read-only; the effective set a user sees = global merged with their own.
- Backend CRUD in `agent.py` (`save_/delete_/toggle_user_*`, `describe_*`); endpoints under `routes/`.

### Memory (two deepagents primitives)

- `/memory/AGENTS.md` — always-loaded core memory, served from `UserConfig.agents_md` via `MemoryBackend` (deepagents `MemoryMiddleware`). Single doc per user; the agent edits it with `edit_file`.
- `/memories/` — dynamic per-user scratch folder backed by a LangGraph `StoreBackend` (cross-thread, namespaced `(uid, "memories")`); the agent creates/reads files freely. The Memory tab shows both (AGENTS.md editor + the `/memories/` file list).

### Sandboxed execution (OpenSandbox) — gated by `SANDBOX_ENABLED`

When off, the agent uses the host `SessionFilesystemBackend` (files under `data/<uid>/workspace/<seg>`). When on, per-`(user, thread)` execution runs in an **OpenSandbox** container:

- `sandbox.py` — lifecycle manager. Owns ONE dedicated background event loop (the async OpenSandbox SDK + the pool/lock must all live on it): `run_sync` (sync callers via `to_thread`) / `run_async` (main-loop callers). Pool keyed by `workspace_id`; **durability = a Docker named volume per workspace** mounted at `/workspace` (outlives the ephemeral sandbox); reaper pauses idle, `_enforce_cap` LRU-pauses beyond `max_live`.
- `sandbox_backend.py` — `OpenSandboxBackend(deepagents BaseSandbox)`: sync `execute`/`upload`/`download` bridged via `sandbox.run_sync` over the SDK; `_w()` remaps agent paths into the `/workspace` mount (the sandbox prompt sets cwd there, so write_file args are absolute `/workspace/...`).
- `workspace_sandbox.py` — async dock FS facade for `/v1/workspace/*` when sandbox on. `routes/workspace.py` branches sandbox-vs-host per op; `_norm_path()` strips the mount prefix so agent-recorded `/workspace/foo` and dock-relative `foo` resolve identically in **both** backends.
- The OpenSandbox **server** runs separately on `:8090` (`uvx --from opensandbox-server opensandbox-server --config sandbox.toml`, started by `start_all.sh`; needs Docker). The image is `sandbox-image/Dockerfile` → **`joyjoy/sandbox-fat:<N>`**, multi-language (Python, Node.js, Java, Go, Rust, C/C++ + Playwright/browsers + data/media/doc tooling). `config.sandbox_image` must match the built tag; `start_all.sh` builds it if absent. **New chats use the configured image; existing pooled sandboxes keep their image until idle-reaped.**

### HITL tool approval & auto-approve

The runs API (`runs.py`) compiles the agent with `interrupt_on` gating all MCP tools (+ `execute` when sandbox on). Approval is resolved **server-side** in `_drive`: per-chat `Session.auto_approve` (+ account default `UserConfig.auto_approve_default`) is sent on `POST /v1/runs`; when on, gates auto-resolve with no card. The composer toggle + the in-card "Allow for rest of chat" button drive it from the SPA.

### Model providers & picker

Five provider types: `azure_openai`, `anthropic` (also Azure AI Foundry `/anthropic` Claude), `bedrock`, `openai` (OpenAI-compatible via base_url), `gemini`. The Settings→Providers add/edit forms render from `describe_providers()` (the `global_providers` table — single source of truth). **API keys are Fernet-encrypted at rest** in each model row's `settings` JSON, masked by `describe_models` (`••••xxxx`); a blank/masked key on edit preserves the stored value. MCP secrets are **not** stored — use `${VAR}` refs (real value in `.env`).

### frontend (`frontend/`) — React SPA

Vite + React 19 + TS (assistant-ui, Tailwind v4, shadcn, TanStack Query, react-i18next), served by the backend. Per-user prefs persist to `UserConfig` via `/v1/settings/ui` (`src/api/prefs.ts` `persistPref()` + `src/components/PrefsSync.tsx` hydration). i18n default = English (`src/i18n/`; `Resources = typeof en` — every locale must have the same keys or tsc fails). The chat runtime + HITL approval surface live in `src/runtime/JoyjoyRuntimeProvider.tsx` and `src/components/assistant-ui/`. Rebuild what the backend serves with `cd frontend && npm run build` (tsc + Biome must be clean).

## Conventions & gotchas

- **Secrets** in `.env` (gitignored): `JWT_SECRET`, `CREDENTIAL_ENCRYPTION_KEY` (generate-once — rotating it orphans every encrypted secret), `AZURE_OPENAI_API_KEY`, `OPENSANDBOX_API_KEY`, `SANDBOX_ENABLED`, etc. At rest, model/provider secrets are **Fernet-encrypted**; the seed SQL carries only `${VAR}` refs.
- **MCP env**: the MCP SDK passes NO inherited env to stdio servers, so `agent._to_connections` injects PATH/HOME/cache; `${VAR}` in MCP command/args/url/env is expanded from `os.environ`. Avoid bare `npx` unless a Linux node is on PATH (it can resolve to Windows npx and hang).
- After any model/MCP/skill/memory write, the agent cache for that user is invalidated — keep new write paths going through the `save_/delete_/toggle_` helpers so this holds.
