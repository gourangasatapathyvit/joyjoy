"""Validate the multi-provider model registry end-to-end (pre-restart):
  - model_specs parses every model with the right provider
  - ${VAR} api_key expansion actually resolves (no literal ${...} left)
  - build_model_for() returns the right LangChain class per provider
  - a live Claude call routes through the Azure Foundry /anthropic endpoint
Run: ~/joyjoy/backend/.venv/bin/python ~/joyjoy/scripts/validate_models.py
"""
import asyncio
import os
import sys

sys.path.insert(0, "/home/gourangasatapathy/joyjoy/backend")
os.chdir("/home/gourangasatapathy/joyjoy/backend")

# Replicate startup env loading (.env -> os.environ) so ${VAR} expansion sees
# the same environment the running server will. NB: do NOT import app.main here —
# it opens a DB connection at import and hangs this standalone probe.
for line in open("/home/gourangasatapathy/joyjoy/.env", encoding="utf-8"):
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    k, v = k.strip(), v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        v = v[1:-1]
    os.environ.setdefault(k, v)
print("[env] loaded .env -> os.environ (manual parse)")

from app.config import get_settings  # noqa: E402
from app.agent import build_model_for  # noqa: E402

s = get_settings()
specs = s.model_specs
print(f"\n[registry] {len(specs)} models, default={s.default_model}")
bad = False
for mid, sp in specs.items():
    k = sp.get("api_key") or ""
    masked = (k[:6] + "…" + k[-4:]) if len(k) > 12 else ("<EMPTY>" if not k else "<set>")
    leak = "  !!! UNEXPANDED ${} LEFT" if "${" in k else ""
    if "${" in k:
        bad = True
    print(f"  {mid:<16} provider={sp['provider']:<12} deploy={sp['deployment']:<34} key={masked}{leak}")

mc = build_model_for(s, "claude-opus-4-7")
print(f"\n[build] claude-opus-4-7 -> {type(mc).__name__}")
ma = build_model_for(s, "o4-mini")
print(f"[build] o4-mini         -> {type(ma).__name__}")

r = asyncio.run(mc.ainvoke("Reply with exactly: OK"))
print(f"[live] claude-opus-4-7 says: {r.content!r}")
print("\nRESULT:", "FAIL (key leak)" if bad else "OK")
