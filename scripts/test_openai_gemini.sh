#!/usr/bin/env bash
# Validate the new OpenAI-compatible + Gemini provider types: schema served,
# CRUD save, picker, and build_model_for -> correct LangChain class (no live call).
set -u
BASE=http://127.0.0.1:8080
KEY=dev-gateway-key-change-me

echo "=== provider types in /v1/models/config ==="
curl -s -H "Authorization: Bearer $KEY" -H "X-User-Id: alice" $BASE/v1/models/config \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print([p["id"] for p in d.get("providers",[])])'

echo "=== add an OpenAI-compatible model (dummy key) ==="
curl -s -X POST $BASE/v1/models/config/save -H "Authorization: Bearer $KEY" -H "X-User-Id: alice" -H "Content-Type: application/json" \
  -d '{"id":"openai-test","provider":"openai","deployment":"gpt-4o","endpoint":"https://openrouter.ai/api/v1","api_key":"sk-dummy-openai-key-123"}'; echo

echo "=== add a Gemini model (dummy key) ==="
curl -s -X POST $BASE/v1/models/config/save -H "Authorization: Bearer $KEY" -H "X-User-Id: alice" -H "Content-Type: application/json" \
  -d '{"id":"gemini-test","provider":"gemini","deployment":"gemini-2.0-flash","api_key":"AIza-dummy-gemini-key-123"}'; echo

echo "=== /v1/models as alice (should include openai-test + gemini-test) ==="
curl -s -H "X-User-Id: alice" $BASE/v1/models | python3 -c 'import sys,json; print([m["id"] for m in json.load(sys.stdin)["data"]])'

echo "=== build_model_for -> class per provider (standalone, no live call, no app.main import) ==="
cd /home/gourangasatapathy/joyjoy/backend
.venv/bin/python - <<'PY'
import os, sys
sys.path.insert(0, "/home/gourangasatapathy/joyjoy/backend")
os.chdir("/home/gourangasatapathy/joyjoy/backend")
for line in open("/home/gourangasatapathy/joyjoy/.env", encoding="utf-8"):
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line: continue
    k, v = line.split("=", 1); k, v = k.strip(), v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'": v = v[1:-1]
    os.environ.setdefault(k, v)
from app.config import get_settings
from app.agent import build_model_for, merged_model_specs
s = get_settings()
specs = merged_model_specs(s, "alice")
for mid in ("openai-test", "gemini-test", "claude-opus-4-7", "o4-mini"):
    if mid in specs:
        print(f"  {mid:<16} -> {type(build_model_for(s, mid, 'alice')).__name__}")
PY

echo "=== cleanup: delete the dummy test models ==="
curl -s -X POST $BASE/v1/models/config/delete -H "Authorization: Bearer $KEY" -H "X-User-Id: alice" -H "Content-Type: application/json" -d '{"id":"openai-test"}'; echo
curl -s -X POST $BASE/v1/models/config/delete -H "Authorization: Bearer $KEY" -H "X-User-Id: alice" -H "Content-Type: application/json" -d '{"id":"gemini-test"}'; echo
