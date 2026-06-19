#!/usr/bin/env bash
# Non-streaming chat as alice with her per-user model (claude-opus-4-7 -> Azure
# Foundry). Proves resolve_model/build_model_for read the per-user catalog.
set -u
BASE=http://127.0.0.1:8080
KEY=dev-gateway-key-change-me
echo "=== chat as alice, model=claude-opus-4-7 (per-user -> Foundry) ==="
curl -s -X POST $BASE/v1/chat/completions \
  -H "Authorization: Bearer $KEY" -H "X-User-Id: alice" \
  -H "X-Hermes-Session-Id: test-claude-peruser" -H "Content-Type: application/json" \
  -d '{"model":"claude-opus-4-7","stream":false,"messages":[{"role":"user","content":"In one short sentence, what model and provider are you?"}]}'
echo
echo "=== same model as bob (NOT in his catalog -> should fall back to global default o4-mini) ==="
curl -s -X POST $BASE/v1/chat/completions \
  -H "Authorization: Bearer $KEY" -H "X-User-Id: bob" \
  -H "X-Hermes-Session-Id: test-bob-fallback" -H "Content-Type: application/json" \
  -d '{"model":"claude-opus-4-7","stream":false,"messages":[{"role":"user","content":"Reply with exactly: BOB OK"}]}'
echo
