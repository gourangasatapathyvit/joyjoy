#!/usr/bin/env bash
cd /home/gourangasatapathy/joyjoy/backend || exit 1
.venv/bin/python -m py_compile app/agent.py && echo COMPILE_OK || { echo COMPILE_FAIL; exit 1; }
fuser -k 8080/tcp 2>/dev/null; sleep 2
setsid .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8080 > /tmp/joyjoy_backend.log 2>&1 < /dev/null & disown
sleep 12
bash /home/gourangasatapathy/joyjoy/scripts/check_mcp.sh
