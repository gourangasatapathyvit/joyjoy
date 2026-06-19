#!/usr/bin/env bash
A=(-H "Authorization: Bearer dev-gateway-key-change-me" -H "X-User-Id: alice")
echo "=== backend /v1/health ==="; curl -s -m 5 http://127.0.0.1:8080/v1/health; echo
echo "=== jira mcp (:9000) up? ==="; curl -s -m 6 -o /dev/null -w "  9000/mcp -> HTTP %{http_code}\n" http://127.0.0.1:9000/mcp
echo "=== /v1/skills (control, should be fast) ==="
curl -s -m 12 "${A[@]}" -o /dev/null -w "  /v1/skills -> HTTP %{http_code} %{time_total}s\n" http://127.0.0.1:8080/v1/skills
echo "=== /v1/mcp/servers RAW (timed, -m 45) ==="
curl -s -m 45 "${A[@]}" -w "\n  [http %{http_code} time %{time_total}s bytes %{size_download}]\n" http://127.0.0.1:8080/v1/mcp/servers | tail -6
echo "=== backend log tail ==="
tail -n 18 /tmp/joyjoy_backend.log
