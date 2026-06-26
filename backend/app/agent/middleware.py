"""Custom agent middleware passed to ``create_deep_agent`` (additive — it does not
replace deepagents' built-in stack)."""

from __future__ import annotations

from langchain.agents.middleware import (
    AgentMiddleware,
    ContextEditingMiddleware,
    ModelCallLimitMiddleware,
    ModelRetryMiddleware,
    ToolCallLimitMiddleware,
)
from langchain_core.messages import AIMessage

from app.core.constants import (
    MODEL_MAX_RETRIES,
    MODEL_RETRY_MAX_DELAY_S,
    MODEL_RUN_CALL_LIMIT,
    TOOL_RUN_CALL_LIMIT,
)


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
    reasoning text — see the helper docstring. Async-only: the agent always runs via
    astream, so only ``awrap_model_call`` is reached (the base sync ``wrap_model_call``
    default is fine for any non-async path)."""

    async def awrap_model_call(self, request, handler):
        return await handler(request.override(messages=_strip_textless_thinking(request.messages)))


# HTTP statuses that are worth retrying (transient): request timeout, conflict, too-
# early, rate-limit, and 5xx. Everything else (400/401/403/404…) won't succeed on a
# retry and would just waste time + tokens.
_TRANSIENT_STATUS = frozenset({408, 409, 425, 429, 500, 502, 503, 504})
# Fallbacks when an exception carries no HTTP status (connection/timeout classes).
_TRANSIENT_NAME_HINTS = (
    "timeout",
    "connection",
    "ratelimit",
    "overloaded",
    "internalserver",
    "serviceunavailable",
    "apiconnection",
    "tryagain",
)


def _is_transient_model_error(exc: BaseException) -> bool:
    """Retry ONLY transient model failures — provider-agnostic (anthropic/openai/httpx
    raise APIStatusError-likes with ``.status_code`` or ``.response.status_code``;
    connection/timeout classes are matched by type name). Returns False for 4xx
    (bad-request/auth/not-found) so we never retry a request that can't succeed."""
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    if isinstance(status, int):
        return status in _TRANSIENT_STATUS
    return any(h in type(exc).__name__.lower() for h in _TRANSIENT_NAME_HINTS)


def agent_middleware() -> list[AgentMiddleware]:
    """Production hardening middleware, added ADDITIVELY to create_deep_agent
    (deepagents' built-in stack — Todo/Skills/Filesystem/SubAgent/Summarization/
    PatchToolCalls/PromptCaching/Memory/HITL — is preserved).

    Order matters for the wrap_model_call chain (outer→inner): sanitize/trim the
    request first, then retry wraps the *actual* model call so each retry re-sends
    the already-cleaned request. The *Limit middlewares use before/after_model and
    are order-independent.
    """
    return [
        # Runaway-loop guards (per user turn). 'end' → stop gracefully, return partial.
        ModelCallLimitMiddleware(run_limit=MODEL_RUN_CALL_LIMIT, exit_behavior="end"),
        ToolCallLimitMiddleware(run_limit=TOOL_RUN_CALL_LIMIT, exit_behavior="end"),
        # Request sanitizers: strip invalid thinking blocks, then prune old tool
        # results once context is huge (complements SummarizationMiddleware).
        StripStaleThinkingMiddleware(),
        ContextEditingMiddleware(),
        # Transient-only retry with jittered exponential backoff — innermost so it
        # wraps just the model call (with the already-sanitized request).
        ModelRetryMiddleware(
            max_retries=MODEL_MAX_RETRIES,
            retry_on=_is_transient_model_error,
            backoff_factor=2.0,
            initial_delay=1.0,
            max_delay=MODEL_RETRY_MAX_DELAY_S,
            jitter=True,
        ),
    ]
