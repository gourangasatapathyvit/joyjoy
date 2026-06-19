#!/usr/bin/env bash
echo "1) Windows folder as seen from WSL (auto-mount, NOT a copy):"
echo "   /mnt/c/spns/mcps/ai-skills-apps/MCPs/mcp-atlassian"
ls -la /mnt/c/spns/mcps/ai-skills-apps/MCPs/mcp-atlassian/*.env 2>/dev/null | sed 's/^/   /'
echo
echo "2) Launcher script I created (real WSL filesystem):"
echo "   /home/gourangasatapathy/joyjoy/scripts/run_atlassian_wsl.sh"
echo
echo "3) Running mcp-atlassian process:"
pid=$(fuser 9000/tcp 2>/dev/null | tr -d ' ')
echo "   pid on :9000 = ${pid:-none}"
[ -n "$pid" ] && echo "   cwd  = $(readlink /proc/$pid/cwd 2>/dev/null)"
[ -n "$pid" ] && { echo -n "   cmd  = "; tr '\0' ' ' < /proc/$pid/cmdline 2>/dev/null; echo; }
echo
echo "4) Where uvx actually fetched the mcp-atlassian package (PyPI -> uv cache, not your Windows .venv):"
du -sh /home/gourangasatapathy/.cache/uv 2>/dev/null | sed 's/^/   /' || echo "   (no ~/.cache/uv)"
