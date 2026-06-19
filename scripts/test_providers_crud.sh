#!/usr/bin/env bash
# Validate the store-backed model catalog + per-user CRUD via the gateway API.
set -u
BASE=http://127.0.0.1:8080
KEY=dev-gateway-key-change-me
FKEY="${AZURE_FOUNDRY_ANTHROPIC_API_KEY:-}"   # key not committed; export this env var to run
FEP='https://swa-it-foundry-cs-ai.services.ai.azure.com/anthropic'

echo "=== 1) /v1/models (global catalog, no user) ==="
curl -s $BASE/v1/models; echo

echo "=== 2) /v1/models as alice (before add) ==="
curl -s -H "X-User-Id: alice" $BASE/v1/models; echo

echo "=== 3) save claude-opus-4-7 as alice's per-user model (anthropic/Foundry) ==="
curl -s -X POST $BASE/v1/models/config/save \
  -H "Authorization: Bearer $KEY" -H "X-User-Id: alice" -H "Content-Type: application/json" \
  -d "{\"id\":\"claude-opus-4-7\",\"provider\":\"anthropic\",\"deployment\":\"claude-opus-4-7\",\"endpoint\":\"$FEP\",\"api_key\":\"$FKEY\",\"max_tokens\":4096}"; echo

echo "=== 4) /v1/models as alice (after add — should include claude) ==="
curl -s -H "X-User-Id: alice" $BASE/v1/models; echo

echo "=== 5) /v1/models/config as alice (global read-only + user, keys MASKED) ==="
curl -s -H "Authorization: Bearer $KEY" -H "X-User-Id: alice" $BASE/v1/models/config; echo

echo "=== 6) LEAK CHECK: is the raw Foundry key present anywhere in the config response? ==="
if curl -s -H "Authorization: Bearer $KEY" -H "X-User-Id: alice" $BASE/v1/models/config | grep -q "$FKEY"; then
  echo "!!! LEAK: raw key found in response"; else echo "OK: no raw key leaked (masked)"; fi

echo "=== 7) saved user file (alice) ==="
cat /home/gourangasatapathy/joyjoy/backend/data/users/alice/models.json 2>/dev/null || echo "(no file)"

echo "=== 8) /v1/models as bob (per-user isolation — should NOT include claude) ==="
curl -s -H "X-User-Id: bob" $BASE/v1/models; echo

echo "=== 9) global read-only guard: try to save over a global id (o4-mini) as alice ==="
curl -s -X POST $BASE/v1/models/config/save \
  -H "Authorization: Bearer $KEY" -H "X-User-Id: alice" -H "Content-Type: application/json" \
  -d '{"id":"o4-mini","provider":"azure_openai","endpoint":"x","api_key":"y","api_version":"z"}'; echo
