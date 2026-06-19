# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

joyjoy is a single-process, multi-tenant **Deep Agents** backend (FastAPI + LangGraph, `backend/`) fronted by a patched copy of **hermes-webui** running in **gateway mode** (`webui/`). One `create_deep_agent()` serves all users; per-user isolation is by LangGraph store namespace `(user_id, "fs")` + `thread_id`. Dev = SQLite + local files; prod = everything in Postgres (stateless pods). `README.md` and `PLAN.md` hold the original design — but PLAN.md's phase checklist is **stale**: phases 0–3, the runs/approval API, and multi-provider models are all done.

## Environment: this project lives in WSL

The repo is at `~/joyjoy` inside **WSL Ubuntu**; you may be launched from Windows. This matters:

- Run all project commands through WSL: `wsl bash -lc "bash ~/joyjoy/scripts/<x>.sh"`. The **Bash tool is Git Bash** (Windows) and mangles `/home/...` paths — don't run project shell logic in it directly.
- Edit WSL files via the UNC path `\\wsl.localhost\Ubuntu\home\gourangasatapathy\joyjoy\...`.
- PowerShell→WSL quoting breaks on parens / `$` / nested quotes. For anything non-trivial, **write a `.sh`/`.py` file and run it** with `wsl bash /abs/path` rather than passing a complex inline command.
- WSL↔Windows are separate network namespaces: a service on the **Windows host is NOT reachable** from the WSL backend (Hyper-V firewall). Run dependencies (e.g. the jira MCP server) **inside WSL** on `127.0.0.1` — see `scripts/run_atlassian_wsl.sh`.

## Running the stack

- **Bring everything up** (idempotent; starts jira MCP :9000 → backend :8080 → webui :8788, skips what's already running): `bash ~/joyjoy/scripts/start_all.sh`
- **Restart one service** after edits: `scripts/restart_backend.sh` · `scripts/restart_webui.sh`. The scripts' own "UP/DOWN" check fires too early (webui needs ~10s) — re-check the port if it says DOWN.
- The backend reads `~/joyjoy/.env` via pydantic `env_file="../.env"`, so it **must be started from `backend/`** (the restart script handles this).
- UI: http://127.0.0.1:8788. Test users `alice` / `bob` (in `webui-state/users.json`).

## venvs are uv-managed — there is no `pip`

`backend/.venv` and `webui/.venv` are created by **uv** and have **no `pip` binary**. Install packages via:

```bash
cd ~/joyjoy/backend && VIRTUAL_ENV="$PWD/.venv" ~/.local/bin/uv pip install <pkg>
```

(run it from a script file, not inline). Backend deps are in `backend/pyproject.toml`, **but the provider SDKs `langchain-anthropic`, `langchain-aws`+`boto3`, and `langchain-google-genai` were installed ad-hoc** and are not yet in pyproject — re-run `scripts/install_bedrock.sh` / `install_gemini.sh` if the venv is rebuilt. `webui/.venv` is independent (pyyaml + cryptography); rebuild with `scripts/make_webui_venv.sh`.

## Lint / tests

- Lint: `ruff` (a dev extra in pyproject).
- There is **no backend unit-test suite**. Validation is done with **integration scripts in `scripts/`** run against a live backend: `test_providers_crud.sh`, `test_peruser_chat.sh`, `test_openai_gemini.sh`, `test_azure_selfcontained.sh`, `validate_models.py`. They curl the gateway with `Authorization: Bearer dev-gateway-key-change-me` and `X-User-Id: <user>`. (`webui/tests/` is hermes's own pytest suite, not joyjoy's.)
- **Never `import app.main` from a standalone script** — it opens a DB connection at import and hangs. Replicate env by parsing `.env` into `os.environ` yourself (see `validate_models.py`).

## Architecture

### Gateway contract (webui ↔ backend)

`webui` runs with `HERMES_WEBUI_CHAT_BACKEND=gateway` → `http://127.0.0.1:8080`. It forwards `Authorization: Bearer <gateway key>`, **`X-User-Id`** (logged-in user → isolation), and `X-Hermes-Session-Id` (→ deepagents `thread_id`). Chat flows through `/v1/runs` + `/v1/runs/{id}/events` (SSE runs API with HITL tool approvals) or `/v1/chat/completions` (plain SSE). All endpoints are in `backend/app/main.py`.

### Backend (`backend/app/`)

- `agent.py` — the core (largest file). `_get_or_build()` compiles one `create_deep_agent()` per `(kind, user_id, model_id)` and caches it (`_AGENT_CACHE`); **`_invalidate_user_cache(uid)` is called on every write** so skill/MCP/model/memory edits take effect on the next message. `build_model_for(settings, model_id, uid)` dispatches by `spec["provider"]` to the right LangChain chat model with lazy imports. MCP loading + per-run approval gating also live here.
- `config.py` — `Settings` (pydantic-settings). `model_specs` = the **global** model catalog read from `config/models.json`; `normalize_model()` adds the provider, `${VAR}` expansion, and Azure fallbacks.
- `persistence.py` — dev↔prod swap keyed on `APP_ENV` (SQLite saver + FilesystemBackend ↔ Postgres saver + StoreBackend). Pinned to `deepagents==0.6.10` (uses its private `StoreBackend._convert_file_data_to_store_value`).
- `context.py` `AgentContext(user_id, thread_id)`; `auth.py` `verify_gateway_key` + `resolve_user_id` (reads `X-User-Id`); `runs.py` the runs/approval engine.

### Capabilities = global (read-only) + per-user (CRUD) — one pattern, four times

Skills, MCP servers, the model catalog, and memory all share the same shape:

- **Global** = a shared file/dir, read-only in the UI: skills `skills/global/`, MCP `config/global.mcp.json`, models `config/models.json`.
- **Per-user** = writable from the webui, under `data/users/<uid>/`: `mcp.json`, `models.json`; skills + memory live in the LangGraph **store** under namespace `(uid, "fs")`.
- Backend CRUD lives in `agent.py` (`save_/delete_/toggle_user_*`, `describe_*`); gateway endpoints in `main.py` (`/v1/skills/*`, `/v1/mcp/servers/*`, `/v1/models/config*`, `/v1/memory*`); webui proxies in `webui/api/routes.py` via `_proxy_gateway_get` / `_proxy_gateway_send` (which forward `X-User-Id`). Writes to a **global** id are rejected as read-only. The effective set a user sees = global merged with their own (`merged_model_specs`, etc.).

### Model providers & picker

Five provider types: `azure_openai`, `anthropic` (also serves Azure AI Foundry's `/anthropic` Claude endpoint), `bedrock`, `openai` (OpenAI-compatible — OpenAI/OpenRouter/DeepSeek/Groq/local via base_url), `gemini`. `PROVIDER_TYPES` in `agent.py` is the field-schema the Settings→Providers tab renders its add/edit forms from. `/v1/models` includes each model's `provider`; the webui `/api/models` proxy groups models into one optgroup per provider for the chat picker. **API keys are stored literally in the gitignored JSON catalog files and never sent to the browser** — `describe_models` masks them (`••••xxxx`), and on edit a blank/masked key field preserves the stored value.

### webui (`webui/`) — patched hermes-webui

Gateway mode. joyjoy-specific surface: `api/routes.py` (gateway proxies, `/api/models` provider-grouping, `_static_cache_token` SW-cache bust), `static/panels.js` (Providers/Skills/MCP/Memory tabs + CRUD), `static/ui.js` (model picker `populateModelDropdown`). Editing any `static/*` file auto-busts the service-worker cache (mtime folded into the `?v=` token), but you still must `restart_webui.sh`.

## Conventions & gotchas

- **Do NOT rename internal `hermes` identifiers** in the webui: `X-Hermes-CSRF-Token`, `X-Hermes-Session-*` headers, the `hermes_session` cookie, `hermes-*` localStorage/cache keys, and `HERMES_WEBUI_*` env vars are load-bearing. (User-facing strings were rebranded to "joyjoy"; these internal ids were deliberately kept.)
- **Secrets** live only in gitignored files: `.env`, `config/models.json` (now holds literal keys), `data/users/*/*.json`. `~/joyjoy` is not currently a git repo, but `.gitignore` is configured for when it becomes one.
- The shared/base model catalog is fully self-contained in **`config/models.json`** (literal keys, no `.env` reference) — edit that JSON directly to change global models; the backend re-reads the file each request (no restart needed). `AZURE_OPENAI_*` env vars were intentionally removed.
- Credentials originate from `deepagent/env.txt` (Windows side) → copied into `~/joyjoy/.env`.
