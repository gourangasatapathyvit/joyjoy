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
```bash
cd ~/joyjoy/backend
uv venv && source .venv/bin/activate
uv pip install -e .
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
curl -s localhost:8080/healthz
```
Then point hermes-webui at it (see PLAN.md §7).
