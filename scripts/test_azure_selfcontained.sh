#!/usr/bin/env bash
# Prove the Azure base models work purely from config/models.json (literal key),
# with NO AZURE_OPENAI_API_KEY in the backend environment.
set -u
BASE=http://127.0.0.1:8080
KEY=dev-gateway-key-change-me

echo "=== azure models in /v1/models/config (key masked, sourced from models.json literal) ==="
curl -s -H "Authorization: Bearer $KEY" -H "X-User-Id: alice" $BASE/v1/models/config \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print([(m["id"],m["api_key_masked"]) for m in d["models"] if m["provider"]=="azure_openai"])'

echo "=== confirm AZURE_OPENAI_API_KEY is NOT set in the backend process env ==="
PID=$(fuser 8080/tcp 2>/dev/null | tr -d ' ')
if [ -n "$PID" ]; then
  n=$(tr '\0' '\n' < /proc/$PID/environ | grep -c '^AZURE_OPENAI_API_KEY=' || true)
  echo "AZURE_OPENAI_API_KEY present in backend env? count=$n (expect 0)"
fi

echo "=== azure chat o4-mini (works only if the literal key from models.json resolves) ==="
curl -s -X POST $BASE/v1/chat/completions -H "Authorization: Bearer $KEY" -H "X-User-Id: alice" \
  -H "X-Hermes-Session-Id: test-azure-selfcontained" -H "Content-Type: application/json" \
  -d '{"model":"o4-mini","stream":false,"messages":[{"role":"user","content":"Reply with exactly: AZURE OK"}]}'
echo
