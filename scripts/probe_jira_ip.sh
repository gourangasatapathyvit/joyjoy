#!/usr/bin/env bash
for ip in 172.30.208.1 172.25.208.1; do
  code=$(curl -s -m 6 -o /dev/null -w "%{http_code}" "http://$ip:9000/mcp" 2>/dev/null)
  echo "  http://$ip:9000/mcp -> HTTP $code   (000=unreachable; 4xx/2xx=reachable)"
done
