# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

joyjoy is a single-process, multi-tenant **Deep Agents** app: a FastAPI + LangGraph backend (`backend/`) that **also serves the React SPA** (`frontend/`, built to `frontend/dist`, mounted via `app.frontend()`) — one process, one origin. One `create_deep_agent()` serves all users; per-user isolation is by the authenticated identity **`User.id` (uuid)** + `thread_id`. **All application data lives in one relational DB** (dev SQLite / prod Postgres, selected by `APP_ENV`); chat messages stay in the LangGraph checkpointer; provider secrets are Fernet-encrypted at rest. The legacy hermes-webui has been **removed**. See `README.md`, `PLAN.md`, and `docs/RUNNING.md`.

## Environment: this project lives in WSL

The repo is at `~/joyjoy` inside **WSL Ubuntu**; you may be launched from Windows. This matters:

- Run all project commands through WSL: `wsl bash -lc "bash ~/joyjoy/scripts/<x>.sh"`. The **Bash tool is Git Bash** (Windows) and mangles `/home/...` paths — don't run project shell logic in it directly.
- Edit WSL files via the UNC path `\\wsl.localhost\Ubuntu\home\gourangasatapathy\joyjoy\...`.
- PowerShell→WSL quoting breaks on parens / `$` / nested quotes. For anything non-trivial, **write a `.sh`/`.py` file and run it** with `wsl bash /abs/path` rather than passing a complex inline command.
- WSL↔Windows are separate network namespaces: a service on the **Windows host is NOT reachable** from the WSL backend (Hyper-V firewall). Run dependencies (e.g. the jira MCP server) **inside WSL** on `127.0.0.1` — see `scripts/run_atlassian_wsl.sh`.

## Running the stack

- **Build SPA + serve everything** on `:8080` (one FastAPI process serves the SPA *and* `/v1`): `bash ~/joyjoy/scripts/serve.sh`
- **Bring everything up** (idempotent; jira MCP :9000 → backend :8080; build the SPA first if stale): `bash ~/joyjoy/scripts/start_all.sh`
- **Restart the backend** after edits: `scripts/restart_backend.sh`. When iterating on the UI only, `cd frontend && npm run dev` (Vite :5173, proxies `/v1` → :8080).
- The backend reads `~/joyjoy/.env` via pydantic `env_file="../.env"`, so it **must be started from `backend/`** (the restart script handles this).
- UI: http://127.0.0.1:8080 — sign up / log in (accounts are in the `users` table). Dev falls back to a seeded dev user when not signed in.

## venvs are uv-managed — there is no `pip`

`backend/.venv` and `webui/.venv` are created by **uv** and have **no `pip` binary**. Install packages via:

```bash
cd ~/joyjoy/backend && VIRTUAL_ENV="$PWD/.venv" ~/.local/bin/uv pip install <pkg>
```

(run it from a script file, not inline). Backend deps are in `backend/pyproject.toml`, **but the provider SDKs `langchain-anthropic`, `langchain-aws`+`boto3`, and `langchain-google-genai` were installed ad-hoc** and are not yet in pyproject — re-run `scripts/install_bedrock.sh` / `install_gemini.sh` if the venv is rebuilt. The frontend is plain npm (`cd frontend && npm install`).

## Lint / tests

- Lint: `ruff` (a dev extra in pyproject).
- There is **no backend unit-test suite**. `scripts/validate_models.py` is a standalone check that `config.model_specs` parses every model + resolves `${VAR}` keys. (The old pre-refactor gateway curl tests — `test_*.sh` with `X-User-Id: alice` — were removed; they assumed the deleted webui gateway + string-identity + store-backed CRUD. Validate against the live `/v1` API with a real session cookie now.)
- **Never `import app.main` from a standalone script** — it opens a DB connection at import and hangs. Replicate env by parsing `.env` into `os.environ` yourself (see `validate_models.py`).

## Architecture

### Frontend ↔ backend (same-origin)

The React SPA calls `/v1/*` same-origin with `credentials: "include"`. Identity comes from an **httpOnly session cookie** whose `sub` is the user's `User.id` (set by `/v1/auth/*`); `resolve_user_id` also accepts an `X-User-Id` header / JWT and, in dev, falls back to a seeded dev user. Chat flows through `/v1/runs` + `/v1/runs/{id}/events` (SSE runs API with HITL tool approvals) or `/v1/chat/completions` (plain SSE). All endpoints are in `backend/app/main.py`; the SPA build is mounted last via `app.frontend()`.

### Backend (`backend/app/`)

- `db/` — the relational layer: `models.py` (13 SQLAlchemy models), `engine.py` (async engine + `db_session()`; SQLite gets a `PRAGMA foreign_keys=ON` connect listener), `crypto.py` (Fernet secrets), `seed.py` (idempotent shipped-catalog seeds). `app_db_url` (in `config.py`) derives dev SQLite / prod Postgres from `APP_ENV`.
- `dbfs.py` — the **DB→agent bridge**: `MemoryBackend` (`/memory/`) + `DbSkillsBackend` (serves BOTH `/skills/user/` with `user_id=uid` and `/skills/global/` with `user_id=None`) deepagents backends mounted in `build_backend`'s `CompositeBackend`. They override the async methods (which CompositeBackend calls) with async DB I/O — **no disk** for skills/memory. Helper files come from `skill_files` (base64-decoded for binaries).
- `agent.py` — the core (largest file). `_get_or_build()` compiles one `create_deep_agent()` per `(kind, user_id, model_id, reasoning)` and caches it (`_AGENT_CACHE`); **`_invalidate_user_cache(uid)` on every write**. `build_model_for` / `resolve_model` / `merged_model_specs` / the model·MCP·skill CRUD are **async** (they read the DB) and decrypt secrets via `db.crypto`. MCP loading + per-run approval gating live here.
- `users.py` accounts + OTP (`users`/`password_resets`); `usersettings.py` UI prefs + memory ↔ `user_configs`; `sessions.py` the `sessions` table.
- `config.py` — `Settings` (pydantic-settings). `model_specs` (config/models.json) is now only the **seed source** + a health-info list. `persistence.py` — LangGraph saver+store, dev↔prod by `APP_ENV` (pinned `deepagents==0.6.10`).
- `context.py` `AgentContext(user_id, thread_id)`; `auth.py` `verify_gateway_key` + `current_user_id`/`resolve_user_id`; `runs.py` the runs/approval engine.

### Capabilities = global (read-only) + per-user (CRUD) — one pattern, four times

Skills, MCP servers, the model catalog, and memory all share the same shape — **all in the DB**:

- **Global** = shipped, read-only catalogs seeded on first boot: `global_skills`(+`skill_files`) (← committed bundle `backend/app/db/seeds/global_skills.json`, regenerate via `scripts/build_global_skills_seed.py`), `global_mcps` (← `config/global.mcp.json`), `global_models`/`global_providers` (← `config/models.json` + `PROVIDER_TYPES`), `skins`. There is no loose `skills/` tree — global skills live entirely in the DB.
- **Per-user** = writable rows keyed by `User.id`: `user_models`, `user_mcps`, `user_skills`(+`skill_files`), and `user_configs` (UI prefs + memory: `notes`/`about_you`/`persona`). Global skills' helper files still live on disk (shipped assets).
- Backend CRUD lives in `agent.py` (`save_/delete_/toggle_user_*`, `describe_*` — async DB); endpoints in `main.py` (`/v1/skills/*`, `/v1/mcp/servers/*`, `/v1/models/config*`, `/v1/memory*`, `/v1/settings/ui`, `/v1/skins`). Writes to a **global** id are rejected as read-only. The effective set a user sees = global merged with their own (`merged_model_specs`, `_merged_mcp_servers`, `list_skills`).

### Model providers & picker

Five provider types: `azure_openai`, `anthropic` (also serves Azure AI Foundry's `/anthropic` Claude endpoint), `bedrock`, `openai` (OpenAI-compatible — OpenAI/OpenRouter/DeepSeek/Groq/local via base_url), `gemini`. `PROVIDER_TYPES` in `agent.py` is the field-schema the Settings→Providers tab renders its add/edit forms from (mirrored in the `global_providers` table). `/v1/models` includes each model's `provider` for the picker. **API keys are Fernet-encrypted at rest** inside the model rows' `settings` JSON and never sent to the browser — `describe_models` masks them (`••••xxxx`), and on edit a blank/masked key field preserves the stored (encrypted) value. (MCP secrets are NOT stored — use `${VAR}` refs; the real value lives in `.env`.)

### frontend (`frontend/`) — React SPA

Vite + React 19 + TS, served by the backend. Per-user prefs (skin/theme/locale/activity/auto-follow/default model+reasoning) persist to `UserConfig` via `/v1/settings/ui`: `src/api/prefs.ts` `persistPref()` writes + keeps the query cache in sync; `src/components/PrefsSync.tsx` hydrates them once after login. Skins load from `/v1/skins`. i18n default = English (`src/i18n/`). See `frontend/README.md`. Rebuild what the backend serves with `cd frontend && npm run build`.

**Multi-file user skills**: user skills are full trees (SKILL.md + helper files), not just an MD. `SkillsPanel.tsx` is a per-skill file-tree workspace (edit files, Add file, delete, Re-import .zip; global = read-only). Endpoints: `POST /v1/skills/files/save` `{skill,path,content,encoding}`, `/v1/skills/files/delete`, `/v1/skills/import` `{name,zip_b64}` (zip is base64 in JSON — no python-multipart). Backend fns in `agent.py`: `save_user_skill_file`/`delete_user_skill_file`/`import_user_skill` (`_safe_rel` blocks path traversal; size/count caps; SKILL.md → `user_skills.content`, others → `skill_files`). The agent serves the whole tree via the same `DbSkillsBackend`.

## Conventions & gotchas

- **Do NOT rename internal `hermes` identifiers** in the webui: `X-Hermes-CSRF-Token`, `X-Hermes-Session-*` headers, the `hermes_session` cookie, `hermes-*` localStorage/cache keys, and `HERMES_WEBUI_*` env vars are load-bearing. (User-facing strings were rebranded to "joyjoy"; these internal ids were deliberately kept.)
- **Secrets** live only in gitignored files: `.env`, `config/models.json` (now holds literal keys), `data/users/*/*.json`. `~/joyjoy` is not currently a git repo, but `.gitignore` is configured for when it becomes one.
- The shared/base model catalog is fully self-contained in **`config/models.json`** (literal keys, no `.env` reference) — edit that JSON directly to change global models; the backend re-reads the file each request (no restart needed). `AZURE_OPENAI_*` env vars were intentionally removed.
- Credentials originate from `deepagent/env.txt` (Windows side) → copied into `~/joyjoy/.env`.
