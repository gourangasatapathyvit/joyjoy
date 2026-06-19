import os
import sys

os.chdir("/home/gourangasatapathy/joyjoy/backend")
sys.path.insert(0, ".")
from app.agent import _expand_env_vars, _to_connections
from app.main import _load_env_file_into_environ

_load_env_file_into_environ()
k = os.environ.get("TAVILY_API_KEY", "")
print("TAVILY_API_KEY loaded into environ:", bool(k), "prefix=", k[:9])
conns = _to_connections({"tavily": {"command": "npx", "args": ["-y", "tavily-mcp@latest"], "env": {"TAVILY_API_KEY": "${TAVILY_API_KEY}"}}})
env = conns["tavily"]["env"]
print("tavily conn env has real key:", env.get("TAVILY_API_KEY", "")[:9], "(not literal ${...}:", env.get("TAVILY_API_KEY") != "${TAVILY_API_KEY}", ")")
print("tavily conn env includes PATH:", "PATH" in env)
