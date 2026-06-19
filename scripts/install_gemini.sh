#!/usr/bin/env bash
# Install Google Gemini provider dep into the uv-managed backend venv.
set -eu
cd /home/gourangasatapathy/joyjoy/backend
export VIRTUAL_ENV="$PWD/.venv"
UV="$(command -v uv || echo "$HOME/.local/bin/uv")"
echo "[install_gemini] using uv: $UV"
"$UV" pip install langchain-google-genai
echo "[install_gemini] --- verify ---"
.venv/bin/python - <<'PY'
import importlib.util as u
for m in ("langchain_google_genai", "langchain_openai"):
    print(m, "OK" if u.find_spec(m) else "MISSING")
PY
