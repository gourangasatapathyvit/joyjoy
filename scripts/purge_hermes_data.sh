#!/usr/bin/env bash
echo "=== removing ~/.hermes (full clean remove) ==="
rm -rf /home/gourangasatapathy/.hermes
echo "rm exit=$?"
echo
echo "=== verify ==="
[ -d /home/gourangasatapathy/.hermes ] && echo "  ~/.hermes STILL PRESENT" || echo "  ~/.hermes GONE (good)"
command -v hermes >/dev/null 2>&1 && echo "  hermes STILL in PATH" || echo "  hermes: command not found (good)"
[ -e /home/gourangasatapathy/.local/bin/hermes ] && echo "  launcher STILL present" || echo "  launcher gone (good)"
echo
echo "=== joyjoy intact ==="
echo "  webui venv  : $([ -x /home/gourangasatapathy/joyjoy/webui/.venv/bin/python ] && echo OK || echo MISSING)"
echo "  backend venv: $([ -x /home/gourangasatapathy/joyjoy/backend/.venv/bin/python ] && echo OK || echo MISSING)"
echo "  uvx         : $(command -v uvx || echo MISSING)"
echo "  global skills: $(find /home/gourangasatapathy/joyjoy/skills/global -maxdepth 2 -name SKILL.md 2>/dev/null | wc -l) SKILL.md"
echo "  webui-state : $([ -f /home/gourangasatapathy/joyjoy/webui-state/users.json ] && echo OK || echo MISSING)"
