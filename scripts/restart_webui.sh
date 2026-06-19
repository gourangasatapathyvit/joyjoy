#!/usr/bin/env bash
# Restart ONLY the joyjoy webui (:8788) to pick up routes.py / static changes.
set -u
log() { echo "[restart_webui] $*"; }

log "stopping :8788 ..."
fuser -k 8788/tcp >/dev/null 2>&1 || true
sleep 2

log "starting joyjoy webui on :8788 ..."
( cd /home/gourangasatapathy/joyjoy/webui && \
  HERMES_WEBUI_AGENT_DIR=/home/gourangasatapathy/.hermes/hermes-agent \
  HERMES_WEBUI_CHAT_BACKEND=gateway \
  HERMES_WEBUI_GATEWAY_API_KEY=dev-gateway-key-change-me \
  HERMES_WEBUI_GATEWAY_BASE_URL=http://127.0.0.1:8080 \
  HERMES_WEBUI_GATEWAY_USE_RUNS_API=true \
  HERMES_WEBUI_HOST=127.0.0.1 HERMES_WEBUI_PORT=8788 \
  HERMES_WEBUI_STATE_DIR=/home/gourangasatapathy/joyjoy/webui-state \
  setsid /home/gourangasatapathy/joyjoy/webui/.venv/bin/python server.py \
  > /tmp/joyjoy_webui.log 2>&1 < /dev/null & disown )

sleep 8
if fuser 8788/tcp >/dev/null 2>&1; then log ":8788 UP"; else log ":8788 DOWN (see /tmp/joyjoy_webui.log)"; fi
