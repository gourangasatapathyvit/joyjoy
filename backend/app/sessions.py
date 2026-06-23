"""Per-user session (conversation thread) registry + thread-message loading.

LangGraph's checkpointer has no thread-list API, so we keep a lightweight
registry in the relational ``sessions`` table — one row per ``thread_id`` holding
``{title, default_model, reasoning, workspace_path, forked_from, timestamps}``.
Conversation messages are read straight from the checkpointer's saved state
(that stays in LangGraph — Postgres in prod, sqlite in dev).
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete as sa_delete
from sqlalchemy import select

from .db import db_session
from .db.models import Session

logger = logging.getLogger("joyjoy.sessions")


def _title_from_text(text: str) -> str:
    first = ""
    for line in (text or "").splitlines():
        if line.strip():
            first = line.strip()
            break
    return first[:80].strip() or "New chat"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _epoch(dt: datetime | None) -> float:
    """Stored datetime -> epoch seconds (frontend Session uses numbers). Naive
    values are treated as UTC (that's how we store them)."""
    if dt is None:
        return 0.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _to_wire(s: Session) -> dict:
    """ORM row -> the wire dict the frontend `Session` type expects."""
    return {
        "thread_id": s.thread_id,
        "title": s.title,
        "created_at": _epoch(s.created_at),
        "updated_at": _epoch(s.updated_at),
        "model": s.default_model or "",
        "reasoning": s.reasoning or "off",
        "workspace_id": s.workspace_path or s.thread_id,
        "forked_from": s.forked_from,
    }


async def record_session(
    user_id: str,
    thread_id: str,
    *,
    first_text: str | None = None,
    model: str | None = None,
    reasoning: str | None = None,
    workspace_id: str | None = None,
) -> None:
    """Upsert a session on run start: create with a title derived from the first
    message, or bump ``updated_at`` (and backfill the title) for an existing one.

    Each session carries a ``workspace_path`` (defaults to its own ``thread_id``)
    — the key for its per-session workspace dir. A forked session shares the
    parent's so both point at the same files."""
    try:
        async with db_session() as s:
            row = await s.get(Session, thread_id)
            if row:
                row.updated_at = _now()
                if model:
                    row.default_model = model
                if reasoning:
                    row.reasoning = reasoning
                if first_text and (not row.title or row.title == "New chat"):
                    row.title = _title_from_text(first_text)
                if not row.workspace_path:
                    row.workspace_path = workspace_id or thread_id
            else:
                s.add(
                    Session(
                        thread_id=thread_id,
                        user_id=str(user_id),
                        title=_title_from_text(first_text or ""),
                        default_model=model or "",
                        reasoning=reasoning or "off",
                        workspace_path=workspace_id or thread_id,
                    )
                )
    except Exception:
        logger.warning("record_session failed", exc_info=True)


async def workspace_id_for(user_id: str, thread_id: str) -> str:
    """The workspace-dir key for a thread: the session's stored ``workspace_path``,
    else the ``thread_id`` itself (so a brand-new chat gets its own workspace)."""
    if not thread_id:
        return "default"
    try:
        async with db_session() as s:
            row = await s.get(Session, thread_id)
            if row and row.user_id == str(user_id):
                return row.workspace_path or thread_id
    except Exception:
        logger.debug("workspace_id_for failed", exc_info=True)
    return thread_id


async def fork_session(user_id: str, src_thread_id: str, *, title: str | None = None) -> dict:
    """Create a new session that SHARES the source session's workspace (same
    files) by inheriting its ``workspace_path``."""
    thread_id = "t-" + uuid.uuid4().hex
    async with db_session() as s:
        src = await s.get(Session, src_thread_id)
        new = Session(
            thread_id=thread_id,
            user_id=str(user_id),
            title=(title or (src.title if src else None) or "New chat"),
            default_model=(src.default_model if src else "") or "",
            reasoning=(src.reasoning if src else "off") or "off",
            workspace_path=(src.workspace_path if src else None) or src_thread_id,
            forked_from=src_thread_id,
        )
        s.add(new)
        await s.flush()
        return _to_wire(new)


async def list_sessions(user_id: str, limit: int = 200) -> list[dict]:
    try:
        async with db_session() as s:
            rows = (
                await s.scalars(
                    select(Session)
                    .where(Session.user_id == str(user_id))
                    .order_by(Session.updated_at.desc())
                    .limit(limit)
                )
            ).all()
            if len(rows) >= limit:
                logger.warning(
                    "session list truncated at %d for user=%s — older conversations not shown",
                    limit,
                    user_id,
                )
            return [_to_wire(r) for r in rows]
    except Exception:
        logger.warning("list_sessions failed", exc_info=True)
        return []


async def create_session(user_id: str, title: str | None = None) -> dict:
    thread_id = "t-" + uuid.uuid4().hex
    async with db_session() as s:
        row = Session(
            thread_id=thread_id,
            user_id=str(user_id),
            title=(title or "").strip()[:120] or "New chat",
            workspace_path=thread_id,
        )
        s.add(row)
        await s.flush()
        return _to_wire(row)


async def rename_session(user_id: str, thread_id: str, title: str) -> dict:
    async with db_session() as s:
        row = await s.get(Session, thread_id)
        if not row or row.user_id != str(user_id):
            return {"ok": False, "error": "not found"}
        row.title = (title or "").strip()[:120] or row.title or "New chat"
        return {"ok": True, "thread_id": thread_id, "title": row.title}


async def delete_session(checkpointer, user_id: str, thread_id: str) -> dict:
    try:
        async with db_session() as s:
            await s.execute(
                sa_delete(Session).where(
                    Session.thread_id == thread_id, Session.user_id == str(user_id)
                )
            )
    except Exception:
        logger.warning("session delete failed", exc_info=True)
    # Best-effort: drop the checkpoint thread too (newer langgraph savers support this).
    try:
        deleter = getattr(checkpointer, "adelete_thread", None)
        if deleter:
            await deleter(thread_id)
    except Exception:
        logger.debug("checkpoint thread delete failed", exc_info=True)
    return {"ok": True, "thread_id": thread_id}


async def session_owner(thread_id: str) -> str | None:
    """Return the owning user id for ``thread_id``, or ``None`` if no such session
    exists yet (e.g. a brand-new thread the client created optimistically before its
    first run persisted it)."""
    try:
        async with db_session() as s:
            return await s.scalar(select(Session.user_id).where(Session.thread_id == thread_id))
    except Exception:
        return None


async def owns_session(user_id: str, thread_id: str) -> bool:
    return await session_owner(thread_id) == str(user_id)


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


async def import_session(agent, user_id: str, messages: list, title: str | None = None) -> dict:
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
    await record_session(user_id, thread_id, first_text=(title or first_user or "Imported chat"))
    return {"ok": True, "thread_id": thread_id, "count": len(msgs)}
