#!/usr/bin/env bash
B=http://127.0.0.1:8080
H=(-s -m 30 -H "Authorization: Bearer dev-gateway-key-change-me" -H "X-User-Id: alice")
echo "=== servers (name scope status tool_count) ==="
curl "${H[@]}" "$B/v1/mcp/servers" | python3 -c 'import sys,json
d=json.load(sys.stdin)
for s in d["servers"]: print(" ", s["name"], s["scope"], s["status"], s["tool_count"])'
echo "=== tools (joyjoy_ping must survive the unreachable jira) ==="
curl "${H[@]}" "$B/v1/mcp/tools" | python3 -c 'import sys,json
d=json.load(sys.stdin)
print(" ", [t["name"] for t in d["tools"]])'
