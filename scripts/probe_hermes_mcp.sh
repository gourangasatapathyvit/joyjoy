#!/usr/bin/env bash
HERMES=/home/gourangasatapathy/.local/bin/hermes
echo "=== hermes mcp --help ==="
"$HERMES" mcp --help 2>&1 | head -60
echo
echo "=== config.yaml location(s) ==="
find /home/gourangasatapathy/.hermes -maxdepth 2 -name "config.y*ml" 2>/dev/null
echo
echo "=== mcp_servers / mcp config blocks ==="
for c in $(find /home/gourangasatapathy/.hermes -maxdepth 2 -name "config.y*ml" 2>/dev/null); do
  echo "--- $c ---"
  grep -n -i "mcp" "$c" 2>/dev/null | head -30
done
