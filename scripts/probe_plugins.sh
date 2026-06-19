#!/usr/bin/env bash
HERMES=/home/gourangasatapathy/.local/bin/hermes
echo "=== hermes plugins list ==="
"$HERMES" plugins list 2>&1 | head -45
echo
echo "=== ~/.hermes/plugins dir ==="
ls -la /home/gourangasatapathy/.hermes/plugins 2>/dev/null || echo "(no plugins dir)"
echo
echo "=== manifest.json under ~/.hermes/plugins ==="
find /home/gourangasatapathy/.hermes/plugins -name manifest.json 2>/dev/null
echo "count_user_plugins=$(find /home/gourangasatapathy/.hermes/plugins -name manifest.json 2>/dev/null | wc -l)"
echo
echo "=== bundled plugins under hermes-agent ==="
find /home/gourangasatapathy/.hermes/hermes-agent -maxdepth 4 -name manifest.json 2>/dev/null | grep -i plugin | head -20
echo "count_bundled=$(find /home/gourangasatapathy/.hermes/hermes-agent -path '*plugin*' -name manifest.json 2>/dev/null | wc -l)"
