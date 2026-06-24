#!/usr/bin/env bash
# Restart ONLY the joyjoy backend (:8080) to pick up app/ changes.
# Loads ~/joyjoy/.env via pydantic (env_file="../.env"), so run from backend/.
set -u
# Repo root = parent of this script's dir (portable; no hardcoded /home/<user>).
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
log() { echo "[restart_backend] $*"; }

log "stopping stray validate_models + :8080 ..."
pkill -f validate_models.py >/dev/null 2>&1 || true
fuser -k 8080/tcp >/dev/null 2>&1 || true
sleep 2

log "starting joyjoy backend on :8080 ..."
( cd "$ROOT/backend" && \
  setsid .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8080 \
  > /tmp/joyjoy_backend.log 2>&1 < /dev/null & disown )

# wait for the port to accept connections (up to ~30s)
for i in $(seq 1 15); do
  if fuser 8080/tcp >/dev/null 2>&1; then log ":8080 UP"; break; fi
  sleep 2
done
fuser 8080/tcp >/dev/null 2>&1 || log ":8080 DOWN (see /tmp/joyjoy_backend.log)"
