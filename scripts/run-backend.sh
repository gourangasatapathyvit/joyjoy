#!/usr/bin/env bash
# Dev runner for the joyjoy backend. DEV_MODE=true (relaxed auth) by default; the DB
# backend follows COMPOSE_PROFILES in .env (devdb=SQLite, localdb/server=Postgres).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE/../backend"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv not found. Install: https://docs.astral.sh/uv/  (or: pip install uv)" >&2
  exit 1
fi

[ -d .venv ] || uv venv
# shellcheck disable=SC1091
source .venv/bin/activate
uv pip install -e . >/dev/null

export DEV_MODE="${DEV_MODE:-true}"
exec uvicorn app.main:app --host "${BACKEND_HOST:-0.0.0.0}" --port "${BACKEND_PORT:-8080}" --reload
