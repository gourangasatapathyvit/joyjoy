#!/usr/bin/env bash
# Install Bedrock provider deps into the uv-managed backend venv.
set -eu
cd /home/gourangasatapathy/joyjoy/backend
export VIRTUAL_ENV="$PWD/.venv"
UV="$(command -v uv || echo "$HOME/.local/bin/uv")"
echo "[install_bedrock] using uv: $UV"
"$UV" pip install langchain-aws boto3
echo "[install_bedrock] --- verify ---"
.venv/bin/python - <<'PY'
import importlib.util as u
for m in ("langchain_aws", "boto3"):
    print(m, "OK" if u.find_spec(m) else "MISSING")
PY
