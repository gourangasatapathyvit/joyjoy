"""Per-user, per-session workspace file browser + CRUD.

Files live under ``<user_data_root>/<uid>/workspace/<workspace_id>`` — the SAME
dir the deepagents ``SessionFilesystemBackend`` (see agent.py) roots at for that
session, so whatever the agent reads/writes in a chat shows up here. The
``workspace_id`` defaults to the chat's ``thread_id`` (so each new chat gets its
own dir); a forked chat shares its parent's ``workspace_id`` → the same files.
Every op is confined to the per-session root (``..``/absolute escapes refused).
"""

from __future__ import annotations

import logging
import mimetypes
import os
import re
import shutil

from .constants import MAX_WORKSPACE_PREVIEW_BYTES

logger = logging.getLogger("joyjoy.workspace")


def _seg(value: str) -> str:
    """Sanitize a workspace id into a single safe path segment (matches the
    agent-side ``SessionFilesystemBackend`` sanitizer so both resolve the same dir)."""
    s = re.sub(r"[^A-Za-z0-9._-]", "_", str(value or ""))[:128]
    return s or "default"


def workspace_root(settings, user_id: str, workspace_id: str) -> str:
    # Root is config-driven (WORKSPACE_ROOT, defaults to USER_DATA_ROOT) so the
    # agent's files and this panel always resolve to the SAME dir — and the root
    # can be repointed at a shared volume / mount for multi-node deployments.
    return os.path.join(
        settings.workspace_root_dir, str(user_id or "default"), "workspace", _seg(workspace_id)
    )


def _safe(root: str, rel: str) -> str | None:
    """Resolve ``rel`` under ``root``, refusing ``..``/absolute escapes."""
    full = os.path.realpath(os.path.join(root, rel or ""))
    rr = os.path.realpath(root)
    return full if full == rr or full.startswith(rr + os.sep) else None


def _is_root(root: str, full: str) -> bool:
    return os.path.realpath(full) == os.path.realpath(root)


def build_tree(settings, user_id: str, workspace_id: str) -> list[dict]:
    """Nested {name, path, type, size?, children?} tree (dirs first, then files)."""
    root = workspace_root(settings, user_id, workspace_id)
    os.makedirs(root, exist_ok=True)

    def walk(dirpath: str) -> list[dict]:
        try:
            names = os.listdir(dirpath)
        except OSError:
            return []
        out: list[dict] = []
        for name in names:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root)
            if os.path.isdir(full):
                out.append(
                    {"name": name, "path": rel, "type": "dir", "children": walk(full)}
                )
            else:
                try:
                    size = os.path.getsize(full)
                except OSError:
                    size = 0
                out.append({"name": name, "path": rel, "type": "file", "size": size})
        out.sort(key=lambda e: (e["type"] != "dir", e["name"].lower()))
        return out

    return walk(root)


def read_file(settings, user_id: str, workspace_id: str, rel: str) -> dict | None:
    """Read a workspace file as UTF-8 text (binary → flagged, no content)."""
    root = workspace_root(settings, user_id, workspace_id)
    full = _safe(root, rel)
    if not full or not os.path.isfile(full):
        return None
    try:
        size = os.path.getsize(full)
        with open(full, "rb") as f:
            raw = f.read(MAX_WORKSPACE_PREVIEW_BYTES + 1)
    except OSError:
        logger.warning("workspace read failed: %s", rel, exc_info=True)
        return None
    truncated = len(raw) > MAX_WORKSPACE_PREVIEW_BYTES
    raw = raw[:MAX_WORKSPACE_PREVIEW_BYTES]
    try:
        return {
            "path": rel,
            "content": raw.decode("utf-8"),
            "size": size,
            "truncated": truncated,
            "binary": False,
        }
    except UnicodeDecodeError:
        return {"path": rel, "content": "", "size": size, "truncated": truncated, "binary": True}


def raw_file(settings, user_id: str, workspace_id: str, rel: str) -> tuple[str, str] | None:
    """Return (absolute path, mime type) for serving raw bytes (images/PDF/etc.)."""
    full = _safe(workspace_root(settings, user_id, workspace_id), rel)
    if not full or not os.path.isfile(full):
        return None
    mime = mimetypes.guess_type(full)[0] or "application/octet-stream"
    return full, mime


# ── Writes (all confined to the per-session root; the root itself is protected) ──
def save_file(settings, user_id: str, workspace_id: str, rel: str, content: str) -> dict:
    root = workspace_root(settings, user_id, workspace_id)
    full = _safe(root, rel)
    if not full or _is_root(root, full):
        return {"ok": False, "error": "invalid path"}
    if os.path.isdir(full):
        return {"ok": False, "error": "path is a directory"}
    try:
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(content or "")
    except OSError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "path": rel}


def make_dir(settings, user_id: str, workspace_id: str, rel: str) -> dict:
    root = workspace_root(settings, user_id, workspace_id)
    full = _safe(root, rel)
    if not full or _is_root(root, full):
        return {"ok": False, "error": "invalid path"}
    try:
        os.makedirs(full, exist_ok=True)
    except OSError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "path": rel}


def delete_path(settings, user_id: str, workspace_id: str, rel: str) -> dict:
    root = workspace_root(settings, user_id, workspace_id)
    full = _safe(root, rel)
    if not full or _is_root(root, full):
        return {"ok": False, "error": "invalid path"}
    if not os.path.exists(full):
        return {"ok": False, "error": "not found"}
    try:
        if os.path.isdir(full):
            shutil.rmtree(full)
        else:
            os.remove(full)
    except OSError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "path": rel}


def rename_path(settings, user_id: str, workspace_id: str, src: str, dst: str) -> dict:
    root = workspace_root(settings, user_id, workspace_id)
    s = _safe(root, src)
    d = _safe(root, dst)
    if not s or not d or _is_root(root, s) or _is_root(root, d):
        return {"ok": False, "error": "invalid path"}
    if not os.path.exists(s):
        return {"ok": False, "error": "source not found"}
    try:
        os.makedirs(os.path.dirname(d), exist_ok=True)
        os.replace(s, d)
    except OSError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "path": os.path.relpath(d, os.path.realpath(root))}


def save_upload(
    settings, user_id: str, workspace_id: str, dir_rel: str, filename: str, data: bytes
) -> dict:
    root = workspace_root(settings, user_id, workspace_id)
    safe_name = os.path.basename(filename or "").strip()
    if not safe_name:
        return {"ok": False, "error": "no filename"}
    full = _safe(root, os.path.join(dir_rel or "", safe_name))
    if not full or _is_root(root, full):
        return {"ok": False, "error": "invalid path"}
    try:
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as f:
            f.write(data)
    except OSError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "path": os.path.relpath(full, os.path.realpath(root))}
