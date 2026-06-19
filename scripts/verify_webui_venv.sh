#!/usr/bin/env bash
echo "=== stop old webui (hermes-venv) + restart via start_all (new venv) ==="
fuser -k 8788/tcp 2>/dev/null; sleep 2
bash /home/gourangasatapathy/joyjoy/scripts/start_all.sh
echo
echo "=== webui log tail (watch for ImportError / tracebacks) ==="
tail -n 12 /tmp/joyjoy_webui.log
echo
echo "=== which python is the webui actually running on? ==="
pid=$(fuser 8788/tcp 2>/dev/null | tr -d ' ')
[ -n "$pid" ] && readlink /proc/$pid/exe
echo
echo "=== does it serve? ==="
curl -s -m 8 -o /dev/null -w "  GET / -> HTTP %{http_code}\n" http://127.0.0.1:8788/
curl -s -m 8 -o /dev/null -w "  GET /health -> HTTP %{http_code}\n" http://127.0.0.1:8788/health
