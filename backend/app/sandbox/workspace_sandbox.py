"""Workspace dock ops backed by the per-user OpenSandbox filesystem (used when
``settings.sandbox_enabled``). Mirrors the return shapes of ``workspace.py`` so the
``/v1/workspace/*`` routes are backend-agnostic. All ops run on the sandbox loop
(acquire + FS call as one coroutine) via ``sandbox.run_async``.

Every op takes BOTH ``user_id`` (which shared container to acquire) and
``thread_seg`` (which subfolder of that container to confine to — the same
value the agent's own sandbox tools are confined to, so the dock always shows
exactly what the agent can see, never a sibling thread's files).
"""

from __future__ import annotations

import logging
import mimetypes
import posixpath
import shlex
import uuid

from opensandbox.models.filesystem import DirectoryListEntry, MoveEntry, WriteEntry

from app.sandbox import sandbox as sbx
from app.sandbox.confine import confine
from app.core.config import Settings
from app.core.constants import MAX_DOWNLOAD_BYTES, MAX_WORKSPACE_PREVIEW_BYTES
from app.core.textutils import safe_segment

logger = logging.getLogger("joyjoy.workspace")

_TREE_DEPTH = 20


def _mount(settings: Settings) -> str:
    return settings.sandbox_mount_path.rstrip("/") or "/workspace"


def _thread_mount(settings: Settings, thread_seg: str) -> str:
    return f"{_mount(settings)}/{safe_segment(thread_seg) or 'default'}"


def _abs(settings: Settings, thread_seg: str, rel: str) -> str | None:
    """Resolve a workspace path to an absolute sandbox path CONFINED TO the
    current thread's own subfolder, refusing ``..`` escapes (including into a
    sibling thread's subfolder in the same shared container).

    Accepts both workspace-relative paths (``brand/logo.svg`` — what the dock
    tree emits) and absolute mount-prefixed paths (``/workspace/<thread>/brand/logo.svg``
    — what the agent's write_file/edit_file tool calls record, since the sandbox
    prompt sets its working dir to the thread's own subfolder). Both must resolve
    to the same file."""
    return confine(_thread_mount(settings, thread_seg), rel or "")


def _is_dir(entry) -> bool:
    et = (getattr(entry, "entry_type", "") or "").lower()
    return et.startswith("dir") or et == "directory"


async def _tree_impl(settings: Settings, user_id: str, thread_seg: str) -> list[dict]:
    sb, _ = await sbx._acquire(settings, user_id)
    root_dir = _thread_mount(settings, thread_seg)
    entries = await sb.files.list_directory(DirectoryListEntry(path=root_dir, depth=_TREE_DEPTH))
    # Build a nested tree from the flat entry list (paths are absolute under root_dir).
    root: dict = {"children": {}}
    for e in entries:
        rel = posixpath.relpath(e.path, root_dir)
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


async def _read_impl(settings: Settings, user_id: str, thread_seg: str, rel: str) -> dict | None:
    full = _abs(settings, thread_seg, rel)
    if not full:
        return None
    sb, _ = await sbx._acquire(settings, user_id)
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


async def _raw_impl(settings: Settings, user_id: str, thread_seg: str, rel: str) -> tuple[bytes, str] | None:
    full = _abs(settings, thread_seg, rel)
    if not full:
        return None
    sb, _ = await sbx._acquire(settings, user_id)
    try:
        data = await sb.files.read_bytes(full)
    except Exception:  # noqa: BLE001
        return None
    mime = mimetypes.guess_type(full)[0] or "application/octet-stream"
    return bytes(data), mime


async def _write_impl(settings: Settings, user_id: str, thread_seg: str, rel: str, content: str) -> dict:
    full = _abs(settings, thread_seg, rel)
    if not full or full == _thread_mount(settings, thread_seg):
        return {"ok": False, "error": "invalid path"}
    sb, _ = await sbx._acquire(settings, user_id)
    try:
        await sb.files.write_files([WriteEntry(path=full, data=(content or "").encode("utf-8"))])
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
    return {"ok": True, "path": rel}


async def _mkdir_impl(settings: Settings, user_id: str, thread_seg: str, rel: str) -> dict:
    full = _abs(settings, thread_seg, rel)
    if not full or full == _thread_mount(settings, thread_seg):
        return {"ok": False, "error": "invalid path"}
    sb, _ = await sbx._acquire(settings, user_id)
    try:
        await sb.files.create_directories([WriteEntry(path=full)])
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
    return {"ok": True, "path": rel}


async def _delete_impl(settings: Settings, user_id: str, thread_seg: str, rel: str) -> dict:
    full = _abs(settings, thread_seg, rel)
    if not full or full == _thread_mount(settings, thread_seg):
        return {"ok": False, "error": "invalid path"}
    sb, _ = await sbx._acquire(settings, user_id)
    try:
        await sb.files.delete_files([full])
    except Exception:  # noqa: BLE001 - maybe a directory
        try:
            await sb.files.delete_directories([full])
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}
    return {"ok": True, "path": rel}


async def _rename_impl(settings: Settings, user_id: str, thread_seg: str, src: str, dst: str) -> dict:
    root_dir = _thread_mount(settings, thread_seg)
    s, d = _abs(settings, thread_seg, src), _abs(settings, thread_seg, dst)
    if not s or not d or s == root_dir or d == root_dir:
        return {"ok": False, "error": "invalid path"}
    sb, _ = await sbx._acquire(settings, user_id)
    try:
        await sb.files.move_files([MoveEntry(src=s, dest=d)])
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
    return {"ok": True, "path": dst.lstrip("/")}


async def _upload_impl(
    settings: Settings, user_id: str, thread_seg: str, dir_rel: str, filename: str, data: bytes,
) -> dict:
    safe_name = posixpath.basename((filename or "").strip())
    if not safe_name:
        return {"ok": False, "error": "no filename"}
    full = _abs(settings, thread_seg, posixpath.join(dir_rel or "", safe_name))
    root_dir = _thread_mount(settings, thread_seg)
    if not full or full == root_dir:
        return {"ok": False, "error": "invalid path"}
    sb, _ = await sbx._acquire(settings, user_id)
    try:
        await sb.files.write_files([WriteEntry(path=full, data=bytes(data))])
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
    return {"ok": True, "path": posixpath.relpath(full, root_dir)}


# --- public async facade (dispatch onto the sandbox loop) --------------------
async def tree(settings, user_id, thread_seg):
    return await sbx.run_async(_tree_impl(settings, user_id, thread_seg))


async def read_file(settings, user_id, thread_seg, rel):
    return await sbx.run_async(_read_impl(settings, user_id, thread_seg, rel))


async def raw_file(settings, user_id, thread_seg, rel):
    return await sbx.run_async(_raw_impl(settings, user_id, thread_seg, rel))


def _find_node(nodes: list[dict], rel: str) -> dict | None:
    for n in nodes:
        if n["path"] == rel:
            return n
        if n["type"] == "dir" and n.get("children"):
            hit = _find_node(n["children"], rel)
            if hit:
                return hit
    return None


async def _download_impl(settings: Settings, user_id: str, thread_seg: str, rel: str) -> tuple[bytes, str, str] | None:
    """Download from INSIDE the sandbox — the bytes never leave it except as the
    final payload. A single file is read directly; a directory (rel="" = whole
    thread workspace) is zipped *in the sandbox* (``shutil.make_archive`` via the
    shell) into an ephemeral ``/tmp`` archive, read out once, then deleted. We do
    NOT pull every file to the host to re-zip. Capped at MAX_DOWNLOAD_BYTES."""
    root_dir = _thread_mount(settings, thread_seg)
    # File-vs-dir + existence come from the tree listing (reliable across the SDK).
    is_dir = not rel
    if rel:
        node = _find_node(await _tree_impl(settings, user_id, thread_seg), rel)
        if node is None:
            return None
        is_dir = node["type"] == "dir"
    sb, _ = await sbx._acquire(settings, user_id)
    if not is_dir:
        # Single file → raw bytes, standard download.
        full = _abs(settings, thread_seg, rel)
        if full is None:
            return None
        try:
            data = await sb.files.read_bytes(full)
        except Exception:  # noqa: BLE001
            return None
        mime = mimetypes.guess_type(full)[0] or "application/octet-stream"
        return bytes(data), mime, posixpath.basename(rel)
    # Directory (or whole thread workspace) → zip it INSIDE the sandbox. Archive
    # lives in /tmp (outside the zipped tree → no self-inclusion), read once,
    # then removed.
    label = posixpath.basename(rel) or "workspace"
    arch = f"/tmp/joyjoy-dl-{uuid.uuid4().hex}.zip"
    target = rel or "."  # base_dir relative to root_dir (cwd)
    # argv-passed paths (shlex.quote) → no shell injection from the request path.
    script = "import shutil,sys; shutil.make_archive(sys.argv[1], 'zip', '.', sys.argv[2])"
    cmd = (
        f"cd {shlex.quote(root_dir)} && python3 -c {shlex.quote(script)} "
        f"{shlex.quote(arch[:-4])} {shlex.quote(target)}"
    )
    try:
        execution = await sb.commands.run(cmd)
    except Exception:  # noqa: BLE001
        return None
    if getattr(execution, "exit_code", 0) not in (0, None):
        logger.warning("workspace zip failed (exit=%s)", getattr(execution, "exit_code", None))
        return None
    try:
        data = await sb.files.read_bytes(arch)
    except Exception:  # noqa: BLE001
        return None
    finally:
        try:
            await sb.commands.run(f"rm -f {shlex.quote(arch)}")
        except Exception:  # noqa: BLE001
            pass
    if data is None or len(data) > MAX_DOWNLOAD_BYTES:
        return None
    return bytes(data), "application/zip", f"{label}.zip"


async def download(settings, user_id, thread_seg, rel):
    return await sbx.run_async(_download_impl(settings, user_id, thread_seg, rel))


async def save_file(settings, user_id, thread_seg, rel, content):
    return await sbx.run_async(_write_impl(settings, user_id, thread_seg, rel, content))


async def make_dir(settings, user_id, thread_seg, rel):
    return await sbx.run_async(_mkdir_impl(settings, user_id, thread_seg, rel))


async def delete_path(settings, user_id, thread_seg, rel):
    return await sbx.run_async(_delete_impl(settings, user_id, thread_seg, rel))


async def rename_path(settings, user_id, thread_seg, src, dst):
    return await sbx.run_async(_rename_impl(settings, user_id, thread_seg, src, dst))


async def save_upload(settings, user_id, thread_seg, dir_rel, filename, data):
    return await sbx.run_async(_upload_impl(settings, user_id, thread_seg, dir_rel, filename, data))


async def _materialize_impl(settings: Settings, user_id: str, dest_base: str, files: list[tuple[str, bytes]]) -> int:
    """Skills materialize directly under the shared per-user mount (``{mount}/.skills/<name>``),
    deliberately OUTSIDE any thread subfolder — they're shared across all of a
    user's threads, so this takes ``user_id`` only, no thread confinement."""
    sb, _ = await sbx._acquire(settings, user_id)
    base = dest_base.rstrip("/")
    entries = [WriteEntry(path=f"{base}/{rel.lstrip('/')}", data=data) for rel, data in files]
    await sb.files.write_files(entries)
    return len(entries)


async def materialize(settings, user_id, dest_base: str, files: list[tuple[str, bytes]]) -> int:
    """Write a set of ``(relpath, bytes)`` files into the user's sandbox under
    ``dest_base`` (used to drop a skill's tree in so its scripts can run)."""
    return await sbx.run_async(_materialize_impl(settings, user_id, dest_base, files))
