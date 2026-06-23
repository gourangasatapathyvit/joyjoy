"""joyjoy workspace-fs MCP server (stdio): mutating ops on the CURRENT session's
workspace that the deepagents built-in file tools don't provide — delete, move,
and mkdir.

Scoping (two layers, both enforced outside the model's control):
  - JOYJOY_USER_ID + WORKSPACE_ROOT are injected into this server's env per-caller
    by joyjoy's MCP loader, so a server instance is bound to ONE user's tree.
  - `workspace_id` identifies the conversation/thread; joyjoy's tool wrapper fills
    it from the runtime context, so the model only ever passes `path`.
Every op resolves under <WORKSPACE_ROOT>/<JOYJOY_USER_ID>/workspace/<workspace_id>/
and reuses app.workspace's vetted ``..``/absolute-escape confinement (one source
of truth — the same code the UI workspace panel + agent backend use).
"""

import os
import sys
from pathlib import Path

# Make the backend package importable no matter what cwd the server is launched in.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mcp.server.fastmcp import FastMCP  # noqa: E402

from app import workspace as ws  # noqa: E402
from app.config import get_settings  # noqa: E402

mcp = FastMCP("workspace-fs")
# Settings picks up WORKSPACE_ROOT (absolute, injected by the loader) from the env;
# workspace_root_dir is then absolute so paths resolve the same as the main process.
_settings = get_settings()


def _uid() -> str:
    return os.environ.get("JOYJOY_USER_ID", "") or "default"


@mcp.tool()
def delete_file(path: str, workspace_id: str = "") -> str:
    """Delete a file or folder from the current session's workspace.

    path: workspace-relative target (e.g. ``lorem.txt``, ``data/old.csv``).
    workspace_id: leave empty — joyjoy sets it to the current conversation.
    """
    res = ws.delete_path(_settings, _uid(), workspace_id, path)
    return f"Deleted {path}." if res.get("ok") else f"Error: {res.get('error')}"


@mcp.tool()
def move_file(src: str, dst: str, workspace_id: str = "") -> str:
    """Move or rename a file/folder within the current session's workspace.

    src/dst: workspace-relative paths. workspace_id: leave empty.
    """
    res = ws.rename_path(_settings, _uid(), workspace_id, src, dst)
    return f"Moved {src} -> {dst}." if res.get("ok") else f"Error: {res.get('error')}"


@mcp.tool()
def make_dir(path: str, workspace_id: str = "") -> str:
    """Create a folder in the current session's workspace.

    path: workspace-relative folder. workspace_id: leave empty.
    """
    res = ws.make_dir(_settings, _uid(), workspace_id, path)
    return f"Created {path}/." if res.get("ok") else f"Error: {res.get('error')}"


if __name__ == "__main__":
    mcp.run()  # stdio transport
