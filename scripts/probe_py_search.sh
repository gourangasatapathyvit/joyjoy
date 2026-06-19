#!/usr/bin/env bash
UVX=/home/gourangasatapathy/.local/bin/uvx
# load TAVILY key from joyjoy .env for the tavily candidate
TAVILY_API_KEY=$(grep -m1 '^TAVILY_API_KEY=' /home/gourangasatapathy/joyjoy/.env | cut -d= -f2- | tr -d '"' | tr -d ' ')
export TAVILY_API_KEY
for pkg in mcp-tavily tavily-mcp-server mcp-server-tavily duckduckgo-mcp-server mcp-server-fetch; do
  echo "=== uvx $pkg (45s) ==="
  timeout 45 "$UVX" "$pkg" </dev/null >/tmp/uvx_probe.log 2>&1
  rc=$?
  echo "  exit=$rc  (124 = downloaded+started+killed = GOOD; else see log)"
  tail -3 /tmp/uvx_probe.log | sed 's/^/    /'
  echo
done
