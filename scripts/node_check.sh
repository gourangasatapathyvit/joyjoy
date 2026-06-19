#!/usr/bin/env bash
echo "=== PATH entries with node/hermes/local ==="
echo "$PATH" | tr ':' '\n' | grep -iE "node|hermes|/\.local/bin|nodejs" || echo "(none)"
echo "=== node ==="
command -v node && node --version 2>&1 || echo "  node: NOT FOUND"
echo "=== npx (what login shell resolves) ==="
command -v npx && ls -la "$(command -v npx)" && echo "  -> resolves to: $(readlink -f "$(command -v npx)" 2>/dev/null)"
echo "=== ~/.hermes/node (purged?) ==="
ls -ld /home/gourangasatapathy/.hermes/node 2>/dev/null || echo "  GONE"
echo "=== system node? ==="
ls -la /usr/bin/node /usr/local/bin/node /home/gourangasatapathy/.local/bin/node 2>/dev/null || echo "  no system/local node"
echo "=== uv-managed node? ==="
ls /home/gourangasatapathy/.local/share/uv/ 2>/dev/null | head
