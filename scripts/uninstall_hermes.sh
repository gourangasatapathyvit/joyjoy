#!/usr/bin/env bash
echo "=== BEFORE: command -v hermes = $(command -v hermes || echo none) ==="
echo
echo "=== hermes uninstall --full --yes  (remove EVERYTHING incl data) ==="
timeout 180 hermes uninstall --full --yes 2>&1 | tail -50
echo
echo "=== AFTER: hermes removal ==="
echo "  command -v hermes: $(command -v hermes || echo NONE)"
[ -e /home/gourangasatapathy/.local/bin/hermes ] && echo "  launcher STILL PRESENT (will remove)" || echo "  launcher gone (good)"
[ -d /home/gourangasatapathy/.hermes ] && { echo "  ~/.hermes STILL PRESENT:"; ls -la /home/gourangasatapathy/.hermes 2>/dev/null | head; } || echo "  ~/.hermes gone (good)"
echo
echo "=== joyjoy + MCP tools intact? ==="
[ -x /home/gourangasatapathy/joyjoy/webui/.venv/bin/python ] && echo "  webui venv OK" || echo "  webui venv MISSING!"
[ -x /home/gourangasatapathy/joyjoy/backend/.venv/bin/python ] && echo "  backend venv OK" || echo "  backend venv MISSING!"
echo "  uvx: $(command -v uvx || echo MISSING)"
echo "  global skills: $(find /home/gourangasatapathy/joyjoy/skills/global -maxdepth 2 -name SKILL.md 2>/dev/null | wc -l) SKILL.md files"
