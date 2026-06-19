import asyncio
import os
import sys
import time

os.chdir("/home/gourangasatapathy/joyjoy/backend")
sys.path.insert(0, ".")
from app.main import _load_env_file_into_environ  # noqa: E402

_load_env_file_into_environ()
from langchain_mcp_adapters.client import MultiServerMCPClient  # noqa: E402


async def main():
    key = os.environ.get("TAVILY_API_KEY", "")
    env = {k: os.environ[k] for k in ("PATH", "HOME", "USER", "LANG", "XDG_CACHE_HOME") if k in os.environ}
    env["TAVILY_API_KEY"] = key
    conn = {
        "transport": "stdio",
        "command": "/home/gourangasatapathy/.local/bin/uvx",
        "args": ["mcp-tavily"],
        "env": env,
    }
    print("key present:", bool(key), "| uvx exists:", os.path.exists("/home/gourangasatapathy/.local/bin/uvx"))
    t0 = time.time()
    try:
        tools = await asyncio.wait_for(MultiServerMCPClient({"tavily": conn}).get_tools(), timeout=150)
        print(f"OK in {time.time()-t0:.1f}s -- {len(tools)} tool(s):")
        for t in tools:
            print("  -", getattr(t, "name", "?"), "::", (getattr(t, "description", "") or "")[:65])
    except Exception as e:  # noqa: BLE001
        print(f"FAILED after {time.time()-t0:.1f}s: {type(e).__name__}: {e}")


asyncio.run(main())
