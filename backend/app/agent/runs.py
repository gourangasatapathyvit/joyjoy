"""Runs API: tool-progress streaming + HITL approvals over the gateway contract.

Flow:
  POST /v1/runs                 -> {run_id}; spawns a background task driving the agent.
  GET  /v1/runs/{id}/events     -> SSE: message.delta / tool.started / tool.completed /
                                   approval.request / run.completed / run.failed / [DONE]
  POST /v1/runs/{id}/approvals/{aid}/respond -> resume a paused (interrupted) run.
  POST /v1/runs/{id}/cancel

HITL: the agent is compiled with ``interrupt_on`` (HumanInTheLoopMiddleware). When a
gated tool is called the graph interrupts; we surface ``approval.request``, await the
user's decision, then resume with ``Command(resume={"decisions": [...]})``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    HumanMessage,
    RemoveMessage,
    ToolMessage,
)
from langgraph.types import Command

from app.workspace import media as media_mod
from app.agent.agent import _content_to_text, reasoning_text_from_message
from app.core.context import AgentContext

logger = logging.getLogger("joyjoy.runs")


class _Run:
    def __init__(self, run_id: str, agent, ctx: AgentContext, text: str, auto_approve: bool = False,
                 replace_turns: int = 0):
        self.run_id = run_id
        self.agent = agent
        self.ctx = ctx
        self.text = text
        # Per-thread HITL policy captured at run start: when true, gated tools are
        # approved server-side (no approval.request emitted, no client round-trip).
        self.auto_approve = auto_approve
        # Edit/regenerate: drop this many trailing USER turns from the thread
        # checkpoint before appending this run's message (0 = plain append).
        self.replace_turns = replace_turns
        self.queue: asyncio.Queue = asyncio.Queue()
        self.pending: dict[str, asyncio.Future] = {}  # approval_id -> future(decision)
        self.final_text = ""
        self.cancelled = False
        self.task = None
        # Citations collected this turn (ordered, deduped by key) → emitted as a
        # `sources` event at completion. ANY referenced external content becomes a
        # source: fetched/searched URLs, files read, and links in the answer.
        self.sources: dict[str, dict] = {}
        # Latest token usage seen this turn (most recent model call) → persisted for
        # the Context Display badge so it survives reloads.
        self.last_usage: dict | None = None
        # Id of this turn's answer message → sources are persisted keyed by it so
        # each assistant turn keeps its own citations across reloads.
        self.answer_id: str | None = None


_RUNS: dict[str, _Run] = {}

# Matches bare http(s) URLs in tool results / answer text for citation extraction.
_URL_RE = re.compile(r"""https?://[^\s<>()\[\]"'`]+""")


def _add_source(
    run: "_Run", *, kind: str, url: str | None = None, title: str | None = None, name: str | None = None
) -> None:
    """Add a citation (deduped by url|name|title). kind is 'url' or 'document'."""
    key = url or name or title
    if not key or key in run.sources:
        return
    src: dict[str, str] = {"sourceType": kind}
    if url:
        src["url"] = url.rstrip(".,);")
    if title:
        src["title"] = title
    if name:
        src["name"] = name
    run.sources[key] = src


def _collect_tool_sources(run: "_Run", name: str | None, args) -> None:
    """Cite what a tool referenced: http(s) URL args (fetch/search/etc.) become
    url sources; read_file paths become document sources. Generic by design so any
    URL-bearing tool contributes citations, not just web fetch."""
    a = args if isinstance(args, dict) else {}
    for v in a.values():
        if isinstance(v, str) and v.startswith(("http://", "https://")):
            _add_source(run, kind="url", url=v, title=v)
    fp = a.get("file_path") or a.get("path")
    if name == "read_file" and isinstance(fp, str) and fp:
        _add_source(run, kind="document", name=fp.rsplit("/", 1)[-1], title=fp)


def _config(ctx: AgentContext) -> dict:
    return {"configurable": {"thread_id": ctx.thread_id or "default", "user_id": ctx.user_id}}


async def _truncate_trailing_turns(run: _Run, turns: int) -> None:
    """Drop the last ``turns`` USER turns (each HumanMessage + everything after it)
    from the thread checkpoint, so an edited/regenerated message replaces its turn
    instead of accumulating. Uses the framework-supported edit path — RemoveMessage
    tombstones via deepagents' messages reducer + LangGraph ``aupdate_state`` — not
    a manual checkpoint rewrite; message ids are stamped by ``ensure_message_ids``."""
    cfg = _config(run.ctx)
    try:
        snap = await run.agent.aget_state(cfg)
    except Exception:
        logger.warning("truncate: aget_state failed", exc_info=True)
        return
    values = getattr(snap, "values", None) or {}
    msgs = values.get("messages") if isinstance(values, dict) else None
    if not msgs:
        return
    human_idx = [i for i, m in enumerate(msgs) if isinstance(m, HumanMessage)]
    if not human_idx:
        return
    # Cut at the (turns-th from end) HumanMessage; clamp to the first if asked to
    # drop more turns than exist (editing the first message → reset the thread).
    cut = human_idx[-turns] if turns <= len(human_idx) else human_idx[0]
    to_remove = [m for m in msgs[cut:] if getattr(m, "id", None)]
    if to_remove:
        await run.agent.aupdate_state(cfg, {"messages": [RemoveMessage(id=m.id) for m in to_remove]})


async def _emit(run: _Run, event: str, **fields) -> None:
    await run.queue.put({"event": event, **fields})


def _fmt(args) -> str:
    try:
        return json.dumps(args, ensure_ascii=False)[:2000]
    except Exception:
        return str(args)[:2000]


# Canonical reasoning-text extractor lives in agent.py (shared with the model-test probe).
_reasoning_from_msg = reasoning_text_from_message


async def _stream_segment(run: _Run, agent_input):
    """Run one astream segment. Returns ('interrupt', hitl) | ('done', None) | ('cancelled', None)."""
    cfg = _config(run.ctx)
    try:
        it = run.agent.astream(agent_input, config=cfg, context=run.ctx, stream_mode=["messages", "updates"])
    except TypeError:
        it = run.agent.astream(agent_input, config=cfg, stream_mode=["messages", "updates"])
    interrupt_val = None
    async for mode, chunk in it:
        if run.cancelled:
            return "cancelled", None
        if mode == "messages":
            msg = chunk[0] if isinstance(chunk, (tuple, list)) else chunk
            if isinstance(msg, AIMessageChunk):
                rtxt = _reasoning_from_msg(msg)
                if rtxt:
                    await _emit(run, "reasoning.available", text=rtxt, delta=rtxt)
                txt = _content_to_text(getattr(msg, "content", ""))
                if txt:
                    run.final_text += txt
                    await _emit(run, "message.delta", delta=txt)
        elif mode == "updates" and isinstance(chunk, dict):
            if "__interrupt__" in chunk:
                # Record the interrupt but let the stream finish naturally, so the
                # checkpoint is committed/released cleanly before we resume.
                intr = chunk.get("__interrupt__")
                if intr:
                    interrupt_val = getattr(intr[0], "value", None)
                continue
            for _node, upd in chunk.items():
                msgs = upd.get("messages") if isinstance(upd, dict) else None
                # A node may bypass the reducer with langgraph's Overwrite wrapper
                # ({"messages": Overwrite(value=[...])}) — unwrap to the real list.
                if msgs is not None and not isinstance(msgs, list) and hasattr(msgs, "value"):
                    msgs = msgs.value
                for m in (msgs or []):
                    if isinstance(m, AIMessage):
                        # The final answer is the last AIMessage of the turn — keep its
                        # id so its citations persist keyed to it.
                        if getattr(m, "id", None):
                            run.answer_id = m.id
                        # Token usage for the Context Display badge — each model call
                        # reports usage_metadata; the frontend keeps the latest (the
                        # most recent call's input_tokens = current context fill).
                        um = getattr(m, "usage_metadata", None)
                        if um:
                            itd = um.get("input_token_details") or {}
                            otd = um.get("output_token_details") or {}
                            usage = {
                                "input_tokens": um.get("input_tokens"),
                                "output_tokens": um.get("output_tokens"),
                                "total_tokens": um.get("total_tokens"),
                                # Richer breakdown for the Context Display tooltip
                                # (cache hits and reasoning tokens, when reported).
                                "cached_input_tokens": itd.get("cache_read"),
                                "reasoning_tokens": otd.get("reasoning"),
                            }
                            run.last_usage = {k: v for k, v in usage.items() if v is not None}
                            await _emit(run, "usage", **run.last_usage)
                        for tc in (getattr(m, "tool_calls", None) or []):
                            _collect_tool_sources(run, tc.get("name"), tc.get("args"))
                            await _emit(run, "tool.started", tool=tc.get("name"), name=tc.get("name"),
                                        toolCallId=tc.get("id"), args=tc.get("args") or {}, label=tc.get("name"))
                    elif isinstance(m, ToolMessage):
                        err = getattr(m, "status", None) == "error"
                        # Binary read_file results carry base64 media blocks (otherwise
                        # flattened away by _content_to_text) — surface them for rendering.
                        media = media_mod.media_from_message(m)
                        await _emit(run, "tool.completed", tool=getattr(m, "name", None),
                                    name=getattr(m, "name", None), toolCallId=getattr(m, "tool_call_id", None),
                                    status="error" if err else "completed", is_error=err,
                                    result=_content_to_text(getattr(m, "content", ""))[:4000],
                                    media=media)
    return ("interrupt", interrupt_val) if interrupt_val is not None else ("done", None)


async def _drive(run: _Run) -> None:
    # Edit/regenerate: prune the superseded turn(s) from the checkpoint BEFORE the
    # new message is appended, so history reflects only the edited turn.
    if run.replace_turns > 0:
        await _truncate_trailing_turns(run, run.replace_turns)
    agent_input = {"messages": [HumanMessage(run.text)]}
    try:
        while True:
            status, val = await _stream_segment(run, agent_input)
            if run.cancelled or status == "cancelled":
                await _emit(run, "run.cancelled")
                return
            if status == "interrupt":
                action_requests = (val or {}).get("action_requests") if isinstance(val, dict) else None
                action_requests = action_requests or []
                # Auto-approve mode: resolve every gate server-side without surfacing
                # a card. Tools still streamed their started/completed events above, so
                # the calls remain visible; we just skip the human round-trip.
                if run.auto_approve:
                    agent_input = Command(resume={"decisions": [{"type": "approve"} for _ in action_requests]})
                    continue
                futs: list[asyncio.Future] = []
                for ar in action_requests:
                    aid = "ap-" + uuid.uuid4().hex
                    fut = asyncio.get_running_loop().create_future()
                    run.pending[aid] = fut
                    await _emit(
                        run, "approval.request",
                        approval_id=aid, run_id=run.run_id,
                        tool=ar.get("name"), name=ar.get("name"),
                        args=ar.get("args") or {}, command=_fmt(ar.get("args") or {}),
                        description=ar.get("description") or ("Approve " + str(ar.get("name")) + "?"),
                        risk_level="high", choices=["approve", "reject"], allow_permanent=False,
                    )
                    futs.append(fut)
                decisions = [await f for f in futs]
                agent_input = Command(resume={"decisions": decisions})
                continue
            # URLs in the final answer are explicit citations too — merge, then emit
            # the deduped citation set for this turn (any kind: web, file, search…).
            for u in _URL_RE.findall(run.final_text or ""):
                _add_source(run, kind="url", url=u, title=u)
            src_list = list(run.sources.values())
            if src_list:
                await _emit(run, "sources", sources=src_list, message_id=run.answer_id)
            # Persist usage (thread-level) + sources (keyed by this answer's message
            # id) so the badge and per-message Sources footers repopulate on reload.
            if run.last_usage is not None or src_list:
                from app.stores import sessions as _sessions

                await _sessions.set_thread_meta(
                    run.ctx.thread_id,
                    usage=run.last_usage,
                    message_id=run.answer_id,
                    sources=src_list,
                )
            await _emit(run, "run.completed", output=run.final_text)
            return
    except Exception as exc:  # noqa: BLE001 - surface to the event stream
        logger.exception("run %s failed", run.run_id)
        await _emit(run, "run.failed", error=str(exc))
    finally:
        await run.queue.put({"event": "__end__"})


async def start_run(agent, ctx: AgentContext, text: str, *, auto_approve: bool = False,
                    replace_turns: int = 0) -> str:
    run_id = "run-" + uuid.uuid4().hex
    run = _Run(run_id, agent, ctx, text, auto_approve=auto_approve, replace_turns=replace_turns)
    _RUNS[run_id] = run
    run.task = asyncio.create_task(_drive(run))
    return run_id


async def event_stream(run_id: str):
    run = _RUNS.get(run_id)
    if run is None:
        yield {"event": "run.failed", "error": "unknown run_id"}
        return
    try:
        while True:
            ev = await run.queue.get()
            if ev.get("event") == "__end__":
                break
            yield ev
    finally:
        _RUNS.pop(run_id, None)


def respond_approval(run_id: str, approval_id: str, choice: str) -> bool:
    run = _RUNS.get(run_id)
    if run is None:
        return False
    fut = run.pending.pop(approval_id, None)
    if fut is None or fut.done():
        return False
    reject = str(choice or "").strip().lower() in ("reject", "deny", "denied", "no", "decline")
    decision = {"type": "reject"} if reject else {"type": "approve"}
    try:
        fut.get_loop().call_soon_threadsafe(fut.set_result, decision)
    except Exception:
        return False
    return True


def cancel_run(run_id: str) -> bool:
    run = _RUNS.get(run_id)
    if run is None:
        return False
    run.cancelled = True
    for fut in list(run.pending.values()):
        if not fut.done():
            try:
                fut.get_loop().call_soon_threadsafe(fut.set_result, {"type": "reject"})
            except Exception:
                pass
    return True
