#!/usr/bin/env bash
# Bring up the whole joyjoy dev stack. Idempotent: skips anything already running.
# Run from Windows:  wsl bash -lc "bash ~/joyjoy/scripts/start_all.sh"
# Or inside WSL:      bash ~/joyjoy/scripts/start_all.sh
set -u
log() { echo "[start_all] $*"; }
running() { fuser "$1/tcp" >/dev/null 2>&1; }

# 1) jira MCP server (mcp-atlassian) on :9000  -- start BEFORE the backend so its warm-up sees jira
if running 9000; then log ":9000 jira MCP already running"; else
  log "starting jira MCP (mcp-atlassian) on :9000 ..."
  ( cd /mnt/c/spns/mcps/ai-skills-apps/MCPs/mcp-atlassian && \
    setsid uvx mcp-atlassian --env-file mcp-atlassian.basic.env --transport streamable-http --port 9000 --host 127.0.0.1 --stateless \
    > /tmp/mcp_atlassian.log 2>&1 < /dev/null & disown )
fi

# 2) joyjoy backend on :8080 — serves BOTH the React SPA and the /v1 API (single
#    server). Build the SPA first if it's stale:  cd frontend && npm run build
#    (or use scripts/serve.sh, which builds then serves).
if running 8080; then log ":8080 backend already running"; else
  log "starting joyjoy backend on :8080 (SPA + /v1 API) ..."
  ( cd /home/gourangasatapathy/joyjoy/backend && \
    setsid .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8080 \
    > /tmp/joyjoy_backend.log 2>&1 < /dev/null & disown )
fi

sleep 12
log "--- status ---"
for p in 9000 8080; do running "$p" && log "  :$p UP" || log "  :$p DOWN (see /tmp logs)"; done
log "UI: http://127.0.0.1:8080   (sign up / log in; jira/web-search tools are gated for approval in chat)"
