"""Workspace dock ops backed by the per-session OpenSandbox filesystem (used when
``settings.sandbox_enabled``). Mirrors the return shapes of ``workspace.py`` so the
``/v1/workspace/*`` routes are backend-agnostic. All ops run on the sandbox loop
(acquire + FS call as one coroutine) via ``sandbox.run_async``.
"""

from __future__ import annotations

import logging
import mimetypes
import posixpath

from opensandbox.models.filesystem import DirectoryListEntry, MoveEntry, WriteEntry

from . import sandbox as sbx
from .config import Settings
from .constants import MAX_WORKSPACE_PREVIEW_BYTES

logger = logging.getLogger("joyjoy.workspace")

_TREE_DEPTH = 20


def _mount(settings: Settings) -> str:
    return settings.sandbox_mount_path.rstrip("/") or "/workspace"


def _abs(settings: Settings, rel: str) -> str | None:
    """Resolve a workspace path to an absolute sandbox path, refusing ``..``
    escapes outside the mount.

    Accepts both workspace-relative paths (``brand/logo.svg`` — what the dock
    tree emits) and absolute mount-prefixed paths (``/workspace/brand/logo.svg``
    — what the agent's write_file/edit_file tool calls record, since the sandbox
    prompt sets its working dir to the mount). Both must resolve to the same file;
    without stripping the prefix the join would double it (``/workspace/workspace/…``)
    and 404 every agent-written media file rendered inline in chat."""
    mount = _mount(settings)
    rel = rel or ""
    if rel == mount:
        rel = ""
    elif rel.startswith(mount + "/"):
        rel = rel[len(mount) + 1:]
    full = posixpath.normpath(posixpath.join(mount, rel.lstrip("/")))
    if full != mount and not full.startswith(mount + "/"):
        return None
    return full


def _is_dir(entry) -> bool:
    et = (getattr(entry, "entry_type", "") or "").lower()
    return et.startswith("dir") or et == "directory"


async def _tree_impl(settings: Settings, workspace_id: str) -> list[dict]:
    sb, _ = await sbx._acquire(settings, workspace_id)
    mount = _mount(settings)
    entries = await sb.files.list_directory(DirectoryListEntry(path=mount, depth=_TREE_DEPTH))
    # Build a nested tree from the flat entry list (paths are absolute under mount).
    root: dict = {"children": {}}
    for e in entries:
        rel = posixpath.relpath(e.path, mount)
        if rel in (".", ""):
            continue
        parts = rel.split("/")
        node = root
        for i, seg in enumerate(parts):
            kids = node["children"]
            if seg not in kids:
                is_last = i == len(parts) - 1
                kids[seg] = {
                    "name": seg,
                    "path": "/".join(parts[: i + 1]),
                    "type": "dir" if (not is_last or _is_dir(e)) else "file",
                    "children": {},
                    "size": getattr(e, "size", 0) if is_last else 0,
                }
            node = kids[seg]

    def to_list(node) -> list[dict]:
        out = []
        for child in node["children"].values():
            entry = {"name": child["name"], "path": child["path"], "type": child["type"]}
            if child["type"] == "dir":
                entry["children"] = to_list(child)
            else:
                entry["size"] = child["size"]
            out.append(entry)
        out.sort(key=lambda x: (x["type"] != "dir", x["name"].lower()))
        return out

    return to_list(root)


async def _read_impl(settings: Settings, workspace_id: str, rel: str) -> dict | None:
    full = _abs(settings, rel)
    if not full:
        return None
    sb, _ = await sbx._acquire(settings, workspace_id)
    try:
        info = (await sb.files.get_file_info([full])).get(full)
    except Exception:  # noqa: BLE001
        info = None
    if info is None:
        return None
    size = getattr(info, "size", 0)
    try:
        text = await sb.files.read_file(full, limit=None)
    except Exception:  # noqa: BLE001 - non-utf8/binary
        return {"path": rel, "content": "", "size": size, "truncated": False, "binary": True}
    truncated = len(text.encode("utf-8")) > MAX_WORKSPACE_PREVIEW_BYTES
    if truncated:
        text = text.encode("utf-8")[:MAX_WORKSPACE_PREVIEW_BYTES].decode("utf-8", "ignore")
    return {"path": rel, "content": text, "size": size, "truncated": truncated, "binary": False}


async def _raw_impl(settings: Settings, workspace_id: str, rel: str) -> tuple[bytes, str] | None:
    full = _abs(settings, rel)
    if not full:
        return None
    sb, _ = await sbx._acquire(settings, workspace_id)
    try:
        data = await sb.files.read_bytes(full)
    except Exception:  # noqa: BLE001
        return None
    mime = mimetypes.guess_type(full)[0] or "application/octet-stream"
    return bytes(data), mime


async def _write_impl(settings: Settings, workspace_id: str, rel: str, content: str) -> dict:
    full = _abs(settings, rel)
    if not full or full == _mount(settings):
        return {"ok": False, "error": "invalid path"}
    sb, _ = await sbx._acquire(settings, workspace_id)
    try:
        await sb.files.write_files([WriteEntry(path=full, data=(content or "").encode("utf-8"))])
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
    return {"ok": True, "path": rel}


async def _mkdir_impl(settings: Settings, workspace_id: str, rel: str) -> dict:
    full = _abs(settings, rel)
    if not full or full == _mount(settings):
        return {"ok": False, "error": "invalid path"}
    sb, _ = await sbx._acquire(settings, workspace_id)
    try:
        await sb.files.create_directories([WriteEntry(path=full)])
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
    return {"ok": True, "path": rel}


async def _delete_impl(settings: Settings, workspace_id: str, rel: str) -> dict:
    full = _abs(settings, rel)
    if not full or full == _mount(settings):
        return {"ok": False, "error": "invalid path"}
    sb, _ = await sbx._acquire(settings, workspace_id)
    try:
        await sb.files.delete_files([full])
    except Exception:  # noqa: BLE001 - maybe a directory
        try:
            await sb.files.delete_directories([full])
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}
    return {"ok": True, "path": rel}


async def _rename_impl(settings: Settings, workspace_id: str, src: str, dst: str) -> dict:
    s, d = _abs(settings, src), _abs(settings, dst)
    mount = _mount(settings)
    if not s or not d or s == mount or d == mount:
        return {"ok": False, "error": "invalid path"}
    sb, _ = await sbx._acquire(settings, workspace_id)
    try:
        await sb.files.move_files([MoveEntry(src=s, dest=d)])
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
    return {"ok": True, "path": dst.lstrip("/")}


async def _upload_impl(settings: Settings, workspace_id: str, dir_rel: str, filename: str, data: bytes) -> dict:
    safe_name = posixpath.basename((filename or "").strip())
    if not safe_name:
        return {"ok": False, "error": "no filename"}
    full = _abs(settings, posixpath.join(dir_rel or "", safe_name))
    if not full or full == _mount(settings):
        return {"ok": False, "error": "invalid path"}
    sb, _ = await sbx._acquire(settings, workspace_id)
    try:
        await sb.files.write_files([WriteEntry(path=full, data=bytes(data))])
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
    return {"ok": True, "path": posixpath.relpath(full, _mount(settings))}


# --- public async facade (dispatch onto the sandbox loop) --------------------
async def tree(settings, workspace_id):
    return await sbx.run_async(_tree_impl(settings, workspace_id))


async def read_file(settings, workspace_id, rel):
    return await sbx.run_async(_read_impl(settings, workspace_id, rel))


async def raw_file(settings, workspace_id, rel):
    return await sbx.run_async(_raw_impl(settings, workspace_id, rel))


async def save_file(settings, workspace_id, rel, content):
    return await sbx.run_async(_write_impl(settings, workspace_id, rel, content))


async def make_dir(settings, workspace_id, rel):
    return await sbx.run_async(_mkdir_impl(settings, workspace_id, rel))


async def delete_path(settings, workspace_id, rel):
    return await sbx.run_async(_delete_impl(settings, workspace_id, rel))


async def rename_path(settings, workspace_id, src, dst):
    return await sbx.run_async(_rename_impl(settings, workspace_id, src, dst))


async def save_upload(settings, workspace_id, dir_rel, filename, data):
    return await sbx.run_async(_upload_impl(settings, workspace_id, dir_rel, filename, data))


async def _materialize_impl(settings: Settings, workspace_id: str, dest_base: str, files: list[tuple[str, bytes]]) -> int:
    sb, _ = await sbx._acquire(settings, workspace_id)
    base = dest_base.rstrip("/")
    entries = [WriteEntry(path=f"{base}/{rel.lstrip('/')}", data=data) for rel, data in files]
    await sb.files.write_files(entries)
    return len(entries)


async def materialize(settings, workspace_id, dest_base: str, files: list[tuple[str, bytes]]) -> int:
    """Write a set of ``(relpath, bytes)`` files into the session sandbox under
    ``dest_base`` (used to drop a skill's tree in so its scripts can run)."""
    return await sbx.run_async(_materialize_impl(settings, workspace_id, dest_base, files))