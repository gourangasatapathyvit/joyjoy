"""Shared path confinement: normalize a workspace-relative or root-prefixed path
and reject anything that would resolve outside ``root`` (``..`` traversal, a
sibling directory that merely shares a string prefix, etc.). Used both by the
agent's sandbox file tools (confined to a thread's own subfolder) and the
workspace dock (same confinement, same root) — the one thing that keeps a
shared per-user sandbox container from leaking one thread's files into another.
"""

from __future__ import annotations

import posixpath


def confine(root: str, rel_or_abs: str) -> str | None:
    """Resolve ``rel_or_abs`` (workspace-relative, or already prefixed with
    ``root``) to an absolute path under ``root``. Returns ``None`` if the
    resolved path would land outside ``root``."""
    root = root.rstrip("/") or "/"
    rel = rel_or_abs or ""
    if rel == root:
        rel = ""
    elif rel.startswith(root + "/"):
        rel = rel[len(root) + 1 :]
    full = posixpath.normpath(posixpath.join(root, rel.lstrip("/")))
    if full != root and not full.startswith(root + "/"):
        return None
    return full
