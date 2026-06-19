#!/usr/bin/env bash
cd /home/gourangasatapathy/joyjoy/backend || exit 1
.venv/bin/python -m py_compile app/agent.py app/main.py && echo COMPILE_OK || { echo COMPILE_FAIL; exit 1; }
echo "--- pre-downloading tavily-mcp into npx cache ---"
timeout 150 npx -y tavily-mcp@latest </dev/null >/tmp/tavily_dl.log 2>&1
echo "npx exit=$? (124=timed-out-while-serving is fine; it means it launched)"
tail -n 6 /tmp/tavily_dl.log
