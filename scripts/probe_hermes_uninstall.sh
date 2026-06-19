#!/usr/bin/env bash
HERMES=$(command -v hermes)
echo "=== hermes binary ==="
echo "which: $HERMES"
ls -la "$HERMES" 2>/dev/null
echo "--- first lines (shebang/launcher) ---"
head -3 "$HERMES" 2>/dev/null
echo
echo "=== hermes uninstall --help (non-interactive flags?) ==="
hermes uninstall --help 2>&1 | head -40
echo
echo "=== webui dependency on the hermes venv ==="
echo "start_all uses this python for the webui:"
grep -n "hermes-agent/venv/bin/python" /home/gourangasatapathy/joyjoy/scripts/start_all.sh 2>/dev/null
echo "webui own venv present? (would make it independent)"
ls -ld /home/gourangasatapathy/joyjoy/webui/.venv 2>/dev/null || echo "  NO webui/.venv"
echo "webui requirements/pyproject:"
ls /home/gourangasatapathy/joyjoy/webui/requirements*.txt /home/gourangasatapathy/joyjoy/webui/pyproject.toml 2>/dev/null || echo "  (none at top level)"
