"""Minimal demo MCP server (stdio) with one tool, for validating MCP plugin loading."""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("joyjoy-demo")


@mcp.tool()
def joyjoy_ping(text: str) -> str:
    """Echo the given text back with a 'pong:' prefix (demo MCP plugin tool)."""
    return f"pong: {text}"


if __name__ == "__main__":
    mcp.run()  # stdio transport
