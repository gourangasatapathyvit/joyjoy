#!/usr/bin/env bash
echo "=== node / npx / uvx availability ==="
node --version 2>&1; echo "npx: $(command -v npx || echo MISSING)"
echo "uvx: $(command -v uvx || echo MISSING)"; echo "pipx: $(command -v pipx || echo MISSING)"
echo
echo "=== real MCP packages on npm (existence + latest version) ==="
for p in "tavily-mcp" "@playwright/mcp" "@modelcontextprotocol/server-everything"; do
  echo -n "$p -> "; timeout 40 npm view "$p" version 2>/dev/null || echo "(lookup failed)"
done
echo
echo "=== TAVILY key present? ==="
grep -o 'TAVILY_API_KEY=[^[:space:]]\{0,12\}' /home/gourangasatapathy/joyjoy/.env 2>/dev/null | sed 's/\(TAVILY_API_KEY=.\{6\}\).*/\1.../'
