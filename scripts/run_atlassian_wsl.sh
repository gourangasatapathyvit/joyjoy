#!/usr/bin/env bash
PROJ=/mnt/c/spns/mcps/ai-skills-apps/MCPs/mcp-atlassian
cd "$PROJ" || { echo "NO_PROJECT_DIR"; exit 1; }
fuser -k 9000/tcp 2>/dev/null; sleep 1
echo "launching mcp-atlassian in WSL (uvx) on 127.0.0.1:9000 ..."
setsid uvx mcp-atlassian --env-file mcp-atlassian.basic.env --transport streamable-http --port 9000 --host 127.0.0.1 --stateless > /tmp/mcp_atlassian.log 2>&1 < /dev/null & disown
sleep 35
echo "=== log tail ==="
tail -n 20 /tmp/mcp_atlassian.log
echo "=== reachability from WSL ==="
curl -s -m 8 -o /dev/null -w "  127.0.0.1:9000/mcp -> HTTP %{http_code} (000=down, 4xx/2xx=up)\n" http://127.0.0.1:9000/mcp
