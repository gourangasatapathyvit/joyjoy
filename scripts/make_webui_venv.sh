#!/usr/bin/env bash
set -e
cd /home/gourangasatapathy/joyjoy/webui
echo "=== uv venv .venv ==="
uv venv .venv
echo "=== uv pip install -r requirements.txt (pyyaml, cryptography) ==="
uv pip install --python .venv/bin/python -r requirements.txt
echo "=== verify core imports ==="
.venv/bin/python -c "import yaml, cryptography, sys; print('webui venv OK - python', sys.version.split()[0])"
ls -la /home/gourangasatapathy/joyjoy/webui/.venv/bin/python
