#!/usr/bin/env bash
HOSTIP=$(grep -m1 nameserver /etc/resolv.conf 2>/dev/null | awk '{print $2}')
echo "WSL->Windows host gateway (resolv.conf nameserver) = $HOSTIP"
echo
for addr in "localhost" "127.0.0.1" "$HOSTIP"; do
  [ -z "$addr" ] && continue
  code=$(curl -s -m 6 -o /dev/null -w "%{http_code}" "http://$addr:9000/mcp" 2>/dev/null)
  echo "  http://$addr:9000/mcp -> HTTP $code   (000 = unreachable)"
done
echo
echo "=== /etc/resolv.conf ==="; cat /etc/resolv.conf 2>/dev/null | head -5
