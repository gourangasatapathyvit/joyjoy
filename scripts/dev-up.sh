#!/usr/bin/env bash
# One entrypoint that picks the workflow from DEV_MODE in .env (compose itself can't
# branch on an env var to choose a file):
#
#   DEV_MODE=true   → infra-only (docker-compose.dev.yml); you build the SPA and run
#                     the backend on the HOST yourself.
#   DEV_MODE=false  → the full baked stack (docker-compose.yml): SPA + backend built
#                     into one image and run in a container.
#
# COMPOSE_PROFILES (also from .env) selects localdb/devdb/sandbox/observability in both
# cases. Extra args are forwarded to `docker compose` (e.g. `-d`, `--build`, service).
#
#   Run from Windows:  wsl bash -lc "bash ~/joyjoy/scripts/dev-up.sh -d"
#   Or inside WSL:     bash ~/joyjoy/scripts/dev-up.sh -d
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Read DEV_MODE from .env (default false) without sourcing the whole file.
DEV_MODE="$(grep -E '^\s*DEV_MODE\s*=' .env 2>/dev/null | tail -n1 | cut -d= -f2- | tr -d ' "'"'"'' | tr '[:upper:]' '[:lower:]')"
DEV_MODE="${DEV_MODE:-false}"

# Forward extra args if given, else sensible defaults (detached, prune stale services).
if [ "$#" -gt 0 ]; then ARGS=("$@"); else ARGS=(-d --remove-orphans); fi

if [ "$DEV_MODE" = "true" ] || [ "$DEV_MODE" = "1" ]; then
  echo "[dev-up] DEV_MODE=true → infra only (docker-compose.dev.yml)"
  docker compose -f docker-compose.dev.yml up "${ARGS[@]}"
  cat <<'NEXT'

[dev-up] infra is up. Now run the app on the host:
  1) cd frontend && npm run build       # build the SPA the backend serves
  2) cd backend  && uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
     (DEV_MODE=true + your .env are picked up automatically)
NEXT
else
  echo "[dev-up] DEV_MODE=false → full baked stack (docker-compose.yml)"
  docker compose -f docker-compose.yml up --build "${ARGS[@]}"
  echo "[dev-up] stack up → http://localhost:${PORT:-8080}"
fi
