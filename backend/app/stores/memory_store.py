"""Per-user long-term memory CRUD.

Two surfaces, both per-user:
- ``AGENTS.md`` — a single doc in ``user_configs.agents_md``; deepagents'
  MemoryMiddleware loads it into the prompt and the UI Memory panel edits it.
- ``/memories/*`` — dynamic files in the LangGraph store (namespace
  ``(uid,"memories")``); the agent reads/writes them with its file tools and the
  UI manages the SAME entries here. We match the deepagents StoreBackend "v2"
  value shape so the agent and UI stay compatible. A disabled file carries
  ``enabled=False`` in its value (the agent's ``MemoriesBackend`` hides those) —
  one namespace + a value flag, NOT two namespaces, because langgraph's sqlite
  store returns stale ``asearch`` results when the same key lives in two
  namespaces (verified). Toggling is a value update (no move).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.agent.agent_common import invalidate_user_cache as _invalidate_user_cache
from app.core.constants import MEMORIES_LIST_LIMIT
from app.db import db_session, get_or_create_user_config
from app.db.models import UserConfig
from app.stores.dbfs import memories_namespace

logger = logging.getLogger("joyjoy.memory")


async def read_memory(user_id) -> dict:
    """Return {agents_md} text for a user (empty string if unset)."""
    out = {"agents_md": ""}
    try:
        async with db_session() as s:
            cfg = await s.get(UserConfig, str(user_id or ""))
            if cfg:
                out["agents_md"] = getattr(cfg, "agents_md", "") or ""
    except Exception:  # noqa: BLE001
        logger.debug("read_memory failed", exc_info=True)
    return out


async def write_memory(user_id, content) -> dict:
    try:
        async with db_session() as s:
            cfg = await get_or_create_user_config(s, user_id)
            cfg.agents_md = content or ""
    except Exception as e:  # noqa: BLE001
        logger.warning("write_memory failed", exc_info=True)
        return {"ok": False, "error": str(e)}
    _invalidate_user_cache(user_id)  # memory feeds the prompt via MemoryMiddleware
    return {"ok": True}


def _norm_mem_path(path: str) -> str:
    p = (path or "").strip()
    return p if p.startswith("/") else f"/{p}"


def _store_content(value: dict) -> str:
    raw = (value or {}).get("content", "")
    return "\n".join(raw) if isinstance(raw, list) else (raw or "")


def _is_enabled(value: dict) -> bool:
    return (value or {}).get("enabled", True) is not False


async def list_memory_files(store, user_id) -> list[dict]:
    """All /memories/ files: [{path, size, modified_at, enabled}]."""
    if store is None:
        return []
    items = await store.asearch(memories_namespace(user_id), limit=MEMORIES_LIST_LIMIT)
    if len(items) >= MEMORIES_LIST_LIMIT:
        logger.warning(
            "memory file list truncated at %d for user=%s — some files not shown",
            MEMORIES_LIST_LIMIT,
            user_id,
        )
    out = [
        {
            "path": it.key,
            "size": len(_store_content(it.value)),
            "modified_at": (it.value or {}).get("modified_at", ""),
            "enabled": _is_enabled(it.value),
        }
        for it in items
    ]
    out.sort(key=lambda x: x["path"])
    return out


async def read_memory_file(store, user_id, path) -> dict:
    if store is None:
        return {"path": path, "content": "", "enabled": True, "error": "store unavailable"}
    p = _norm_mem_path(path)
    it = await store.aget(memories_namespace(user_id), p)
    if it is None:
        return {"path": p, "content": "", "enabled": True, "error": "not_found"}
    return {"path": p, "content": _store_content(it.value), "enabled": _is_enabled(it.value)}


async def write_memory_file(store, user_id, path, content) -> dict:
    if store is None:
        return {"ok": False, "error": "store unavailable"}
    ns = memories_namespace(user_id)
    p = _norm_mem_path(path)
    if not p.strip("/"):
        return {"ok": False, "error": "path required"}
    now = datetime.now(timezone.utc).isoformat()
    existing = await store.aget(ns, p)
    prev = existing.value if existing else {}
    created = prev.get("created_at") if isinstance(prev.get("created_at"), str) else now
    await store.aput(
        ns,
        p,
        {
            "content": content or "",
            "encoding": "utf-8",
            "created_at": created,
            "modified_at": now,
            "enabled": _is_enabled(prev),  # preserve enabled/disabled across edits
        },
    )
    return {"ok": True, "path": p}


async def toggle_memory_file(store, user_id, path, enabled: bool) -> dict:
    """Enable/disable a memory file via a value update (agent's MemoriesBackend
    hides disabled ones). Single namespace → no stale-search bug."""
    if store is None:
        return {"ok": False, "error": "store unavailable"}
    ns = memories_namespace(user_id)
    p = _norm_mem_path(path)
    it = await store.aget(ns, p)
    if it is None:
        return {"ok": False, "error": "not_found"}
    try:
        await store.aput(ns, p, {**(it.value or {}), "enabled": bool(enabled)})
    except Exception as e:  # noqa: BLE001
        logger.warning("toggle_memory_file failed", exc_info=True)
        return {"ok": False, "error": str(e)}
    return {"ok": True, "enabled": bool(enabled)}


async def delete_memory_file(store, user_id, path) -> dict:
    if store is None:
        return {"ok": False, "error": "store unavailable"}
    try:
        await store.adelete(memories_namespace(user_id), _norm_mem_path(path))
    except Exception as e:  # noqa: BLE001
        logger.warning("delete_memory_file failed", exc_info=True)
        return {"ok": False, "error": str(e)}
    return {"ok": True}
