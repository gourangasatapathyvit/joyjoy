"""Per-user session (conversation thread) registry + thread-message loading.

LangGraph's checkpointer has no thread-list API, so we keep a lightweight
registry in the store under namespace ``(user_id, "sessions")`` — one entry per
``thread_id`` holding ``{thread_id, title, created_at, updated_at, model}``.
Conversation messages are read straight from the checkpointer's saved state.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

logger = logging.getLogger("joyjoy.sessions")

_NS = "sessions"


def _ns(user_id: str) -> tuple[str, str]:
    return (str(user_id or "anonymous"), _NS)


def _title_from_text(text: str) -> str:
    first = ""
    for line in (text or "").splitlines():
        if line.strip():
            first = line.strip()
            break
    return first[:80].strip() or "New chat"


def _value(item: Any) -> dict | None:
    val = getattr(item, "value", None)
    return dict(val) if isinstance(val, dict) else None


async def record_session(
    store,
    user_id: str,
    thread_id: str,
    *,
    first_text: str | None = None,
    model: str | None = None,
    workspace_id: str | None = None,
) -> None:
    """Upsert a session on run start: create with a title derived from the first
    message, or bump ``updated_at`` (and backfill the title) for an existing one.

    Each session carries a ``workspace_id`` (defaults to its own ``thread_id``) —
    the key for its per-session workspace dir. A forked session shares the
    parent's ``workspace_id`` so both point at the same files."""
    ns = _ns(user_id)
    existing = None
    try:
        existing = _value(await store.aget(ns, thread_id))
    except Exception:
        logger.debug("session aget failed", exc_info=True)
    now = time.time()
    if existing:
        val = existing
        val["updated_at"] = now
        if model:
            val["model"] = model
        if first_text and (not val.get("title") or val.get("title") == "New chat"):
            val["title"] = _title_from_text(first_text)
        if not val.get("workspace_id"):
            val["workspace_id"] = workspace_id or thread_id
    else:
        val = {
            "thread_id": thread_id,
            "title": _title_from_text(first_text or ""),
            "created_at": now,
            "updated_at": now,
            "model": model or "",
            "workspace_id": workspace_id or thread_id,
        }
    try:
        await store.aput(ns, thread_id, val)
    except Exception:
        logger.warning("record_session failed", exc_info=True)


async def workspace_id_for(store, user_id: str, thread_id: str) -> str:
    """The workspace-dir key for a thread: the session's stored ``workspace_id``,
    else the ``thread_id`` itself (so a brand-new chat gets its own workspace)."""
    if not thread_id:
        return "default"
    try:
        val = _value(await store.aget(_ns(user_id), thread_id))
    except Exception:
        val = None
    return (val or {}).get("workspace_id") or thread_id


async def fork_session(
    store, user_id: str, src_thread_id: str, *, title: str | None = None
) -> dict:
    """Create a new session that SHARES the source session's workspace (same
    files) by inheriting its ``workspace_id``."""
    src = _value(await store.aget(_ns(user_id), src_thread_id)) or {}
    thread_id = "t-" + uuid.uuid4().hex
    now = time.time()
    val = {
        "thread_id": thread_id,
        "title": (title or src.get("title") or "New chat"),
        "created_at": now,
        "updated_at": now,
        "model": src.get("model", ""),
        "workspace_id": src.get("workspace_id") or src_thread_id,
        "forked_from": src_thread_id,
    }
    await store.aput(_ns(user_id), thread_id, val)
    return val


async def list_sessions(store, user_id: str, limit: int = 200) -> list[dict]:
    try:
        items = await store.asearch(_ns(user_id), limit=limit)
    except Exception:
        logger.warning("list_sessions failed", exc_info=True)
        return []
    out = [v for it in items if (v := _value(it))]
    out.sort(key=lambda s: s.get("updated_at", 0), reverse=True)
    return out


async def create_session(store, user_id: str, title: str | None = None) -> dict:
    thread_id = "t-" + uuid.uuid4().hex
    now = time.time()
    val = {
        "thread_id": thread_id,
        "title": (title or "").strip()[:120] or "New chat",
        "created_at": now,
        "updated_at": now,
        "model": "",
        "workspace_id": thread_id,
    }
    await store.aput(_ns(user_id), thread_id, val)
    return val


async def rename_session(store, user_id: str, thread_id: str, title: str) -> dict:
    ns = _ns(user_id)
    existing = _value(await store.aget(ns, thread_id))
    if not existing:
        return {"ok": False, "error": "not found"}
    existing["title"] = (title or "").strip()[:120] or existing.get("title") or "New chat"
    existing["updated_at"] = time.time()
    await store.aput(ns, thread_id, existing)
    return {"ok": True, "thread_id": thread_id, "title": existing["title"]}


async def delete_session(store, checkpointer, user_id: str, thread_id: str) -> dict:
    try:
        await store.adelete(_ns(user_id), thread_id)
    except Exception:
        logger.warning("session adelete failed", exc_info=True)
    # Best-effort: drop the checkpoint thread too (newer langgraph savers support this).
    try:
        deleter = getattr(checkpointer, "adelete_thread", None)
        if deleter:
            await deleter(thread_id)
    except Exception:
        logger.debug("checkpoint thread delete failed", exc_info=True)
    return {"ok": True, "thread_id": thread_id}


async def owns_session(store, user_id: str, thread_id: str) -> bool:
    try:
        return _value(await store.aget(_ns(user_id), thread_id)) is not None
    except Exception:
        return False


def _serialize_message(m: Any) -> dict | None:
    """Convert a stored LangChain BaseMessage (or raw dict) to a wire dict the
    frontend can rebuild: {role, content, tool_calls?, tool_call_id?, name?, media?}."""
    from app import media as media_mod
    from app.agent import _content_to_text  # local import avoids any import cycle

    role_map = {"human": "user", "ai": "assistant", "tool": "tool", "system": "system"}
    mtype = getattr(m, "type", None)
    if mtype is not None:
        out: dict[str, Any] = {
            "role": role_map.get(mtype, mtype),
            "content": _content_to_text(getattr(m, "content", "")),
        }
        tcs = getattr(m, "tool_calls", None)
        if tcs:
            out["tool_calls"] = [
                {"id": tc.get("id"), "name": tc.get("name"), "args": tc.get("args") or {}}
                for tc in tcs
            ]
        if getattr(m, "tool_call_id", None):
            out["tool_call_id"] = m.tool_call_id
        if getattr(m, "name", None):
            out["name"] = m.name
        media = media_mod.media_from_message(m)
        if media:
            out["media"] = media
        return out
    if isinstance(m, dict) and m.get("role"):
        return {"role": m["role"], "content": str(m.get("content") or "")}
    return None


async def get_thread_messages(agent, user_id: str, thread_id: str) -> list[dict]:
    """Read the persisted messages for a thread from the compiled graph state."""
    config = {"configurable": {"thread_id": thread_id, "user_id": user_id, "checkpoint_ns": ""}}
    try:
        snap = await agent.aget_state(config)
    except Exception:
        logger.warning("aget_state failed for thread %s", thread_id, exc_info=True)
        return []
    values = getattr(snap, "values", None)
    msgs = (values.get("messages") if isinstance(values, dict) else None) or []
    return [d for m in msgs if (d := _serialize_message(m))]


def _deserialize_message(d: dict):
    """Inverse of ``_serialize_message`` — a wire dict back to a LangChain message
    for importing a previously-exported conversation. Accepts BOTH joyjoy's own
    export shape (``tool_calls: [{id, name, args}]``) and the OpenAI / hermes shape
    (``tool_calls: [{id, call_id, function: {name, arguments}}]`` where ``arguments``
    is a JSON string)."""
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

    role = (d or {}).get("role")
    content = (d or {}).get("content") or ""
    if role == "user":
        return HumanMessage(content=content)
    if role == "assistant":
        tool_calls = []
        for t in d.get("tool_calls") or []:
            fn = t.get("function") or {}
            name = t.get("name") or fn.get("name")
            if not name:
                continue
            args = t.get("args")
            if args is None:
                raw = fn.get("arguments")
                if isinstance(raw, dict):
                    args = raw
                elif isinstance(raw, str) and raw.strip():
                    try:
                        args = json.loads(raw)
                    except ValueError:
                        args = {}
                else:
                    args = {}
            tool_calls.append(
                {"id": t.get("id") or t.get("call_id") or "", "name": name, "args": args or {}}
            )
        return AIMessage(content=content, tool_calls=tool_calls)
    if role == "tool":
        return ToolMessage(
            content=content,
            tool_call_id=d.get("tool_call_id") or d.get("call_id") or "imported",
            name=d.get("name") or d.get("tool_name"),
        )
    if role == "system":
        return SystemMessage(content=content)
    return None


async def import_session(agent, store, user_id: str, messages: list, title: str | None = None) -> dict:
    """Create a NEW thread from imported messages (writes them to the graph state)."""
    msgs = [m for d in (messages or []) if (m := _deserialize_message(d))]
    if not msgs:
        return {"ok": False, "error": "no messages to import"}
    thread_id = "t-" + uuid.uuid4().hex
    config = {"configurable": {"thread_id": thread_id, "user_id": user_id, "checkpoint_ns": ""}}
    try:
        await agent.aupdate_state(config, {"messages": msgs})
    except Exception:
        logger.warning("import aupdate_state failed", exc_info=True)
        return {"ok": False, "error": "import failed"}
    first_user = next(
        (d.get("content") for d in messages if (d or {}).get("role") == "user"), ""
    )
    await record_session(
        store, user_id, thread_id, first_text=(title or first_user or "Imported chat")
    )
    return {"ok": True, "thread_id": thread_id, "count": len(msgs)}
