#!/usr/bin/env bash
HERMES=/home/gourangasatapathy/.local/bin/hermes
echo "=== hermes mcp serve --help ==="
"$HERMES" mcp serve --help 2>&1 | head -60
echo
echo "=== hermes mcp list (configured servers hermes knows) ==="
"$HERMES" mcp list 2>&1 | head -40
echo
echo "=== hermes tools list (what tools hermes exposes) ==="
"$HERMES" tools --help 2>&1 | head -20
