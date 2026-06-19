"""Runs API: tool-progress streaming + HITL approvals over the hermes gateway contract.

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
import uuid

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from langgraph.types import Command

from .agent import _content_to_text
from .context import AgentContext

logger = logging.getLogger("joyjoy.runs")


class _Run:
    def __init__(self, run_id: str, agent, ctx: AgentContext, text: str):
        self.run_id = run_id
        self.agent = agent
        self.ctx = ctx
        self.text = text
        self.queue: asyncio.Queue = asyncio.Queue()
        self.pending: dict[str, asyncio.Future] = {}  # approval_id -> future(decision)
        self.final_text = ""
        self.cancelled = False
        self.task = None


_RUNS: dict[str, _Run] = {}


def _config(ctx: AgentContext) -> dict:
    return {"configurable": {"thread_id": ctx.thread_id or "default", "user_id": ctx.user_id}}


async def _emit(run: _Run, event: str, **fields) -> None:
    await run.queue.put({"event": event, **fields})


def _fmt(args) -> str:
    try:
        return json.dumps(args, ensure_ascii=False)[:2000]
    except Exception:
        return str(args)[:2000]


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
                for m in (msgs or []):
                    if isinstance(m, AIMessage) and getattr(m, "tool_calls", None):
                        for tc in m.tool_calls:
                            await _emit(run, "tool.started", tool=tc.get("name"), name=tc.get("name"),
                                        toolCallId=tc.get("id"), args=tc.get("args") or {}, label=tc.get("name"))
                    elif isinstance(m, ToolMessage):
                        err = getattr(m, "status", None) == "error"
                        await _emit(run, "tool.completed", tool=getattr(m, "name", None),
                                    name=getattr(m, "name", None), toolCallId=getattr(m, "tool_call_id", None),
                                    status="error" if err else "completed", is_error=err)
    return ("interrupt", interrupt_val) if interrupt_val is not None else ("done", None)


async def _drive(run: _Run) -> None:
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
            await _emit(run, "run.completed", output=run.final_text)
            return
    except Exception as exc:  # noqa: BLE001 - surface to the event stream
        logger.exception("run %s failed", run.run_id)
        await _emit(run, "run.failed", error=str(exc))
    finally:
        await run.queue.put({"event": "__end__"})


async def start_run(agent, ctx: AgentContext, text: str) -> str:
    run_id = "run-" + uuid.uuid4().hex
    run = _Run(run_id, agent, ctx, text)
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
