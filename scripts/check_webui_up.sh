#!/usr/bin/env bash
pid=$(fuser 8788/tcp 2>/dev/null | tr -d ' ')
echo "webui pid: ${pid:-none}"
[ -n "$pid" ] && echo "python  : $(readlink /proc/$pid/exe)"
curl -s -m 8 -o /dev/null -w "GET /      -> HTTP %{http_code}\n" http://127.0.0.1:8788/
curl -s -m 8 -o /dev/null -w "GET /health -> HTTP %{http_code}\n" http://127.0.0.1:8788/health
