#!/usr/bin/env bash
# Single-server (Phase 4): build the React SPA and serve EVERYTHING — the SPA and
# the /v1 API — from ONE FastAPI process on :8080. No Vite (:5173), no webui
# (:8788). Identity comes from the joyjoy_uid cookie the SPA sets on sign-in;
# the gateway key is disabled (browser is same-origin, single tier).
set -u
ROOT=/home/gourangasatapathy/joyjoy

echo "[serve] building frontend…"
cd "$ROOT/frontend" || exit 1
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh" && nvm use 22 >/dev/null 2>&1
npm run build || { echo "[serve] frontend build FAILED"; exit 1; }

echo "[serve] (re)starting backend on :8080 (serves SPA + /v1)…"
cd "$ROOT/backend" || exit 1
fuser -k 8080/tcp >/dev/null 2>&1 || true
for _ in $(seq 1 10); do fuser 8080/tcp >/dev/null 2>&1 || break; sleep 0.5; done
setsid .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8080 \
  > /tmp/joyjoy_serve.log 2>&1 < /dev/null & disown
for _ in $(seq 1 40); do fuser 8080/tcp >/dev/null 2>&1 && break; sleep 0.5; done
if fuser 8080/tcp >/dev/null 2>&1; then
  echo "[serve] UP — open http://localhost:8080"
else
  echo "[serve] DOWN — log tail:"; tail -20 /tmp/joyjoy_serve.log
fi
