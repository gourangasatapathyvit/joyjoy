"""Custom agent middleware passed to ``create_deep_agent`` (additive — it does not
replace deepagents' built-in stack)."""

from __future__ import annotations

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage


def _is_textless_thinking(block) -> bool:
    """True for a thinking content block that carries NO usable reasoning text —
    i.e. a ``redacted_thinking`` block, or a ``thinking`` block whose ``thinking``
    field is missing/empty (Azure AI Foundry Claude emits signature-only blocks)."""
    if not isinstance(block, dict):
        return False
    t = block.get("type")
    if t == "redacted_thinking":
        return True
    if t == "thinking":
        return not (block.get("thinking") or "").strip()
    return False


def _strip_textless_thinking(messages: list) -> list:
    """Drop only the *textless* thinking blocks from assistant messages, returning a
    (shallow) sanitized copy — the input list is left untouched. Thinking blocks that
    carry real reasoning text are KEPT (they're valid to replay, and they're what the
    UI renders / what standard Anthropic requires back during tool-use continuation).

    WHY: Azure AI Foundry Claude uses ``thinking={"type":"adaptive"}`` and returns
    thinking blocks with only a *signature* and no text (block keys are literally
    ``index/signature/type``). Replaying such a block makes Anthropic reject the whole
    call with ``messages.N.content.0.thinking.thinking: Field required`` — breaking
    BOTH later turns AND same-turn tool-use continuations. Verified against the live
    API: dropping the textless blocks while KEEPING the model's thinking enabled works
    (the model still reasons). We do NOT touch text-bearing thinking blocks, so:
      * standard Anthropic (real thinking text) keeps reasoning in the request — it
        still renders in the UI and stays valid for tool continuation;
      * Foundry (no text) has its invalid blocks removed — nothing renderable is lost.
    This sanitizes only the request COPY sent to the model — the stored checkpoint and
    the UI history are untouched (so it also repairs already-broken threads, no
    migration). Provider-agnostic: non-Anthropic providers never emit these blocks.
    """
    out: list = []
    changed = False
    for m in messages:
        if isinstance(m, AIMessage) and isinstance(m.content, list):
            kept = [b for b in m.content if not _is_textless_thinking(b)]
            if len(kept) != len(m.content):
                out.append(m.model_copy(update={"content": kept}))
                changed = True
                continue
        out.append(m)
    return out if changed else messages


class StripStaleThinkingMiddleware(AgentMiddleware):
    """Drop textless (signature-only / redacted) thinking blocks before each model
    call so Foundry adaptive-thinking chats don't 400, while preserving real
    reasoning text — see the helper docstring."""

    def wrap_model_call(self, request, handler):
        return handler(request.override(messages=_strip_textless_thinking(request.messages)))

    async def awrap_model_call(self, request, handler):
        return await handler(request.override(messages=_strip_textless_thinking(request.messages)))
