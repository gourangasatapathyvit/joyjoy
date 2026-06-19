import asyncio
import time

from langchain_mcp_adapters.client import MultiServerMCPClient


async def main():
    conns = {
        "hermes": {
            "transport": "stdio",
            "command": "/home/gourangasatapathy/.local/bin/hermes",
            "args": ["mcp", "serve", "--accept-hooks"],
        }
    }
    t0 = time.time()
    try:
        tools = await asyncio.wait_for(MultiServerMCPClient(conns).get_tools(), timeout=90)
        print(f"OK in {time.time()-t0:.1f}s -- {len(tools)} tool(s):")
        for t in tools[:40]:
            print("  -", getattr(t, "name", "?"), "::", (getattr(t, "description", "") or "")[:70])
    except Exception as e:  # noqa: BLE001
        print(f"FAILED after {time.time()-t0:.1f}s: {type(e).__name__}: {e}")


asyncio.run(main())
