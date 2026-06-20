# joyjoy

Multi-tenant **Deep Agents** backend (single process, Postgres-backed) with
**hermes-webui** as the chat UI.

- One FastAPI process serves many users; isolation via per-user store namespaces + thread ids.
- **Dev** = SQLite + local files. **Prod** = everything in Postgres (pods are stateless).
- Backend speaks hermes-webui's **gateway** contract, so the existing UI just points at it.

See **[PLAN.md](./PLAN.md)** for the full architecture, the "everything-in-Postgres"
mapping, the required hermes patches, and the phased checklist.

## Layout
- `backend/` — FastAPI + deepagents engine (the new backend)
- `webui/` — patched copy of hermes-webui (the UI)
- `skills/global/`, `config/global.mcp.json` — shared, read-only global skills/MCP
- `data/` — dev sqlite + per-user files (gitignored)

## Quick start (dev)

**Easiest — bring up the whole stack** (idempotent; starts jira MCP `:9000` → backend `:8080` → webui `:8788`, skipping anything already running):
```bash
bash ~/joyjoy/scripts/start_all.sh
# then open  http://127.0.0.1:8788   and log in as  alice  or  bob
```

Or run the two halves by hand:

### 1. Backend — FastAPI + deepagents (`:8080`)
Start it **from `backend/`** so it loads `../.env`:
```bash
cd ~/joyjoy/backend
uv venv && uv pip install -e .          # first time (uv-managed venv; no pip inside it)
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8080   # APP_ENV=dev → SQLite + local files
curl -s localhost:8080/healthz
```

### 2. Frontend — patched hermes-webui in gateway mode (`:8788`)
The webui has its **own** venv and talks to the backend over the gateway contract:
```bash
cd ~/joyjoy/webui
bash ~/joyjoy/scripts/make_webui_venv.sh   # first time → creates webui/.venv
HERMES_WEBUI_CHAT_BACKEND=gateway \
HERMES_WEBUI_GATEWAY_BASE_URL=http://127.0.0.1:8080 \
HERMES_WEBUI_GATEWAY_API_KEY=dev-gateway-key-change-me \
HERMES_WEBUI_GATEWAY_USE_RUNS_API=true \
HERMES_WEBUI_HOST=127.0.0.1 HERMES_WEBUI_PORT=8788 \
HERMES_WEBUI_STATE_DIR="$HOME/joyjoy/webui-state" \
.venv/bin/python server.py
# open  http://127.0.0.1:8788
```

Restart just one service after edits: `scripts/restart_backend.sh` · `scripts/restart_webui.sh`.

**Models** are managed in the UI under **Settings → Providers** (Azure OpenAI, Azure AI Foundry/Claude, Bedrock, OpenAI-compatible, Gemini) or by editing `config/models.json` directly. Architecture details for contributors live in **[CLAUDE.md](./CLAUDE.md)**.
