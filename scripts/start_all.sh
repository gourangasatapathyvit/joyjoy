#!/usr/bin/env bash
# Bring up the WHOLE joyjoy stack in one shot. Idempotent: skips anything already
# running. Order matters — sandbox + jira come up before the backend so its
# startup warm-up can see them.
#
#   FE  = built into frontend/dist and served BY the backend (no separate process)
#   BE  = FastAPI on :8080 (serves the SPA + the /v1 API)
#   OpenSandbox server = :8090 (code/shell execution layer; needs Docker)
#   jira MCP (mcp-atlassian) = :9000
#
# Run from Windows:  wsl bash -lc "bash ~/joyjoy/scripts/start_all.sh"
# Or inside WSL:     bash ~/joyjoy/scripts/start_all.sh
set -u
# Repo root = the parent of this script's dir, resolved at runtime (portable —
# no hardcoded /home/<user> path).
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# uvx from PATH, falling back to the common user-local install location.
UVX="$(command -v uvx 2>/dev/null || echo "$HOME/.local/bin/uvx")"
# jira MCP (mcp-atlassian) lives OUTSIDE the repo; override via env, skip if absent.
JIRA_MCP_DIR="${JIRA_MCP_DIR:-/mnt/c/spns/mcps/ai-skills-apps/MCPs/mcp-atlassian}"
log() { echo "[start_all] $*"; }
running() { fuser "$1/tcp" >/dev/null 2>&1; }

# 0) Docker daemon (OpenSandbox runs sandboxes as Docker containers).
if ! docker info >/dev/null 2>&1; then
  log "WARNING: Docker daemon not reachable — the OpenSandbox server can't create"
  log "         sandboxes. Start Docker, then re-run this script."
fi

# 0.5) Ensure dependencies are installed (first run on a fresh machine). uv sync
#      is idempotent + fast when already in sync; npm install only if missing.
if command -v uv >/dev/null 2>&1; then
  log "ensuring backend deps (uv sync) ..."
  ( cd "$ROOT/backend" && uv sync >/tmp/joyjoy_uv_sync.log 2>&1 ) \
    && log "  backend deps OK" || log "  uv sync FAILED (see /tmp/joyjoy_uv_sync.log)"
else
  log "WARNING: uv not found — install uv (astral.sh/uv) or pre-create backend/.venv"
fi

# 0.6) Ensure the multi-language sandbox image exists (first run = several-minute
#      build). Tag must match config.py sandbox_image; override via SANDBOX_IMAGE.
SANDBOX_IMAGE="${SANDBOX_IMAGE:-joyjoy/sandbox-fat:3}"
if docker image inspect "$SANDBOX_IMAGE" >/dev/null 2>&1; then
  log "sandbox image $SANDBOX_IMAGE present"
else
  log "building sandbox image $SANDBOX_IMAGE (first run, several minutes) ..."
  ( cd "$ROOT" && docker build -t "$SANDBOX_IMAGE" sandbox-image/ >/tmp/joyjoy_sandbox_build.log 2>&1 ) \
    && log "  sandbox image built" || log "  sandbox image build FAILED (see /tmp/joyjoy_sandbox_build.log)"
fi

# 1) OpenSandbox server on :8090 (uvx; config = sandbox.toml, docker runtime).
if running 8090 || pgrep -f opensandbox-server >/dev/null 2>&1; then
  log ":8090 OpenSandbox server already running"
else
  log "starting OpenSandbox server on :8090 ..."
  ( cd "$ROOT" && setsid "$UVX" --from opensandbox-server \
      opensandbox-server --config "$ROOT/sandbox.toml" \
      > /tmp/opensandbox_server.log 2>&1 < /dev/null & disown )
fi

# 2) jira MCP server (mcp-atlassian) on :9000.
if running 9000; then
  log ":9000 jira MCP already running"
elif [ -d "$JIRA_MCP_DIR" ]; then
  log "starting jira MCP (mcp-atlassian) on :9000 ..."
  ( cd "$JIRA_MCP_DIR" && \
    setsid "$UVX" mcp-atlassian --env-file mcp-atlassian.basic.env --transport streamable-http \
      --port 9000 --host 127.0.0.1 --stateless \
    > /tmp/mcp_atlassian.log 2>&1 < /dev/null & disown )
else
  log "jira MCP dir not found ($JIRA_MCP_DIR) — skipping (set JIRA_MCP_DIR to enable)"
fi

# 3) Build the React SPA (the FE the backend serves). Installs node_modules first
#    if missing (fresh machine), then builds (~1-2s) so the backend serves latest.
log "building frontend SPA ..."
( cd "$ROOT/frontend" || exit 1
  export NVM_DIR="$HOME/.nvm"
  [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh" && nvm use 22 >/dev/null 2>&1
  [ -d node_modules ] || npm install
  npm run build ) >/tmp/joyjoy_fe_build.log 2>&1 \
  && log "  SPA built" || log "  SPA build FAILED (see /tmp/joyjoy_fe_build.log)"

# 4) joyjoy backend on :8080 — serves BOTH the SPA and the /v1 API.
if running 8080; then
  log ":8080 backend already running (restart it to pick up a fresh SPA build)"
else
  log "starting joyjoy backend on :8080 (SPA + /v1 API) ..."
  ( cd "$ROOT/backend" && \
    setsid .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8080 \
    > /tmp/joyjoy_backend.log 2>&1 < /dev/null & disown )
fi

sleep 12
log "--- status ---"
for p in 8090 9000 8080; do running "$p" && log "  :$p UP" || log "  :$p DOWN (see /tmp logs)"; done
log "UI: http://127.0.0.1:8080   (sign up / log in)"
