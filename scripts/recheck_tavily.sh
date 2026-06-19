#!/usr/bin/env bash
cd /home/gourangasatapathy/joyjoy/backend || exit 1
.venv/bin/python -m py_compile app/agent.py && echo COMPILE_OK || { echo COMPILE_FAIL; exit 1; }
fuser -k 8080/tcp 2>/dev/null; sleep 2
setsid .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8080 > /tmp/joyjoy_backend.log 2>&1 < /dev/null & disown
sleep 12
B=http://127.0.0.1:8080
H=(-s -m 30 -H "Authorization: Bearer dev-gateway-key-change-me" -H "X-User-Id: alice")
raw=$(curl "${H[@]}" "$B/v1/mcp/servers")
if echo "$raw" | grep -q 'tvly-dev'; then echo "!! REAL KEY LEAKED IN RESPONSE"; else echo "OK: real key NOT in /v1/mcp/servers response"; fi
echo "$raw" | python3 -c 'import sys,json
d=json.load(sys.stdin)
for s in d["servers"]:
  if s["name"]=="tavily": print("tavily env displayed as:", s.get("env"), "status:", s.get("status"), "tools:", s.get("tool_count"))'
