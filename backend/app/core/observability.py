"""Observability: Prometheus metrics + distributed tracing.

Two independent, env-gated layers — both optional, both no-ops unless enabled:

  * **Tracing** (`TRACING_ENABLED`): deepagents runs on LangGraph + LangChain, so
    LangChain's native tracer captures every graph node / LLM call / tool call with
    NO code. We route those traces to a self-hosted **Langfuse** over OTLP via
    LangSmith's built-in OTEL bridge — purely env vars (LANGSMITH_TRACING +
    LANGSMITH_OTEL_ENABLED + OTEL_EXPORTER_OTLP_*). ``setup_tracing`` just flips the
    right flags on from a single toggle and verifies the OTEL packages are present.
    The only code value-add is enriching the run config with metadata/tags/run_name
    (see ``trace_config``), so traces are filterable by user / thread / model.

  * **Metrics** (`METRICS_ENABLED`): a ``prometheus-client`` registry exposed at
    ``/metrics``. App-level HTTP metrics come from ``RequestMetricsMiddleware``;
    agent-level metrics come from explicit ``record_*`` calls in the run loop plus a
    ``PrometheusCallbackHandler`` attached to each agent run (LLM/tool timings).

Label cardinality is kept bounded on purpose — ``model``/``tool``/``decision`` are
small sets; per-user/per-thread detail lives in traces, never in metric labels.
"""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler

logger = logging.getLogger("joyjoy.observability")

# ── Prometheus metrics ───────────────────────────────────────────────────────
# Imported lazily so the dependency is only required when metrics are enabled.
try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        CollectorRegistry,
        Counter,
        Gauge,
        Histogram,
        generate_latest,
    )

    _PROM = True
except Exception:  # pragma: no cover - prometheus-client not installed
    _PROM = False

_LATENCY_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 30, 60, 120, 300)

# Filled by init_metrics(); left None when metrics are disabled so record_* no-op.
REGISTRY: Any = None
_M: dict[str, Any] = {}

# The Langfuse LangChain callback handler, set by setup_tracing() when Langfuse keys
# are configured. Reused across runs (the underlying client is concurrency-safe).
_LANGFUSE_HANDLER: Any = None


def init_metrics() -> bool:
    """Define the metric collectors on a dedicated registry. Idempotent."""
    global REGISTRY, _M
    if not _PROM:
        logger.warning("METRICS_ENABLED but prometheus-client is not installed")
        return False
    if REGISTRY is not None:
        return True
    REGISTRY = CollectorRegistry()
    c = lambda n, d, labels: Counter(n, d, labels, registry=REGISTRY)  # noqa: E731
    h = lambda n, d, labels: Histogram(n, d, labels, buckets=_LATENCY_BUCKETS, registry=REGISTRY)  # noqa: E731
    _M = {
        # agent runs
        "runs": c("joyjoy_agent_runs_total", "Agent runs started", ["model"]),
        "run_errors": c("joyjoy_agent_run_errors_total", "Agent runs that errored", ["model"]),
        "run_seconds": h("joyjoy_agent_run_duration_seconds", "End-to-end agent run latency", ["model"]),
        "active_runs": Gauge("joyjoy_agent_active_runs", "Agent runs in flight", registry=REGISTRY),
        # LLM calls (from the callback handler)
        "llm_calls": c("joyjoy_llm_calls_total", "LLM calls", ["model"]),
        "llm_seconds": h("joyjoy_llm_call_duration_seconds", "LLM call latency", ["model"]),
        "tokens": c("joyjoy_llm_tokens_total", "LLM tokens", ["model", "kind"]),
        # tool calls (from the callback handler)
        "tool_calls": c("joyjoy_tool_calls_total", "Tool calls", ["tool"]),
        "tool_seconds": h("joyjoy_tool_call_duration_seconds", "Tool call latency", ["tool"]),
        "tool_errors": c("joyjoy_tool_errors_total", "Tool errors", ["tool"]),
        # HITL approvals
        "approvals": c("joyjoy_tool_approvals_total", "HITL approval decisions", ["decision"]),
        # HTTP (from RequestMetricsMiddleware)
        "http_requests": c("joyjoy_http_requests_total", "HTTP requests", ["method", "path", "status"]),
        "http_seconds": h("joyjoy_http_request_duration_seconds", "HTTP request latency", ["method", "path"]),
    }
    logger.info("metrics registry initialized (%d collectors)", len(_M))
    return True


def metrics_enabled() -> bool:
    return REGISTRY is not None


# ── record_* helpers — safe no-ops when metrics are disabled ──────────────────
def record_run_start(model: str) -> None:
    if not _M:
        return
    _M["runs"].labels(model).inc()
    _M["active_runs"].inc()


def record_run_end(model: str, seconds: float, *, error: bool = False) -> None:
    if not _M:
        return
    _M["active_runs"].dec()
    _M["run_seconds"].labels(model).observe(seconds)
    if error:
        _M["run_errors"].labels(model).inc()


def record_tokens(model: str, *, input_tokens: int | None, output_tokens: int | None) -> None:
    if not _M:
        return
    if input_tokens:
        _M["tokens"].labels(model, "input").inc(input_tokens)
    if output_tokens:
        _M["tokens"].labels(model, "output").inc(output_tokens)


def record_approval(decision: str) -> None:
    if not _M:
        return
    _M["approvals"].labels(decision).inc()


def render_metrics() -> tuple[bytes, str]:
    """Return (body, content_type) for the /metrics endpoint."""
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST


# ── LangChain callback: per-run LLM/tool timings → Prometheus ────────────────
class PrometheusCallbackHandler(BaseCallbackHandler):
    """Attached to each agent run via ``config={"callbacks": [...]}``. Records LLM
    and tool call counts + latencies. Token totals are recorded in the run loop
    (usage_metadata is parsed there already), so we don't double-count here."""

    def __init__(self, model: str) -> None:
        self.model = model or "unknown"
        self._llm_t0: dict[Any, float] = {}
        self._tool: dict[Any, tuple[str, float]] = {}

    def on_llm_start(self, serialized, prompts, *, run_id=None, **kw) -> None:
        if _M:
            self._llm_t0[run_id] = time.monotonic()

    def on_chat_model_start(self, serialized, messages, *, run_id=None, **kw) -> None:
        if _M:
            self._llm_t0[run_id] = time.monotonic()

    def on_llm_end(self, response, *, run_id=None, **kw) -> None:
        if not _M:
            return
        _M["llm_calls"].labels(self.model).inc()
        t0 = self._llm_t0.pop(run_id, None)
        if t0 is not None:
            _M["llm_seconds"].labels(self.model).observe(time.monotonic() - t0)

    def on_llm_error(self, error, *, run_id=None, **kw) -> None:
        self._llm_t0.pop(run_id, None)

    def on_tool_start(self, serialized, input_str, *, run_id=None, **kw) -> None:
        if not _M:
            return
        name = (serialized or {}).get("name") or "unknown"
        self._tool[run_id] = (name, time.monotonic())
        _M["tool_calls"].labels(name).inc()

    def on_tool_end(self, output, *, run_id=None, **kw) -> None:
        if not _M:
            return
        rec = self._tool.pop(run_id, None)
        if rec:
            name, t0 = rec
            _M["tool_seconds"].labels(name).observe(time.monotonic() - t0)

    def on_tool_error(self, error, *, run_id=None, **kw) -> None:
        if not _M:
            return
        rec = self._tool.pop(run_id, None)
        _M["tool_errors"].labels(rec[0] if rec else "unknown").inc()


# ── Tracing setup ────────────────────────────────────────────────────────────
# Two transports to self-hosted Langfuse, chosen by what's configured:
#   1. Langfuse LangChain callback (PREFERRED) — when LANGFUSE_PUBLIC_KEY/SECRET_KEY
#      are set. Maps langfuse_user_id / langfuse_session_id / langfuse_tags from the
#      run metadata to Langfuse's NATIVE User + Session fields → real per-user and
#      per-session (session-label) views, grouping, and analytics.
#   2. OTLP bridge (fallback) — LangSmith's OTEL export. Vendor-neutral (Tempo/Jaeger
#      too), but user/thread arrive only as generic metadata, not native fields.
def setup_tracing(settings) -> bool:
    global _LANGFUSE_HANDLER
    if not getattr(settings, "tracing_enabled", False):
        return False
    # 1) Langfuse native handler (preferred — gives per-user + per-session).
    if os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY"):
        try:
            from langfuse.langchain import CallbackHandler

            _LANGFUSE_HANDLER = CallbackHandler()
            logger.info(
                "tracing enabled → Langfuse callback (native user/session) host=%s",
                os.environ.get("LANGFUSE_HOST", "default"),
            )
            return True
        except Exception as e:  # pragma: no cover
            logger.warning("Langfuse keys set but handler init failed (%s) — trying OTLP", e)
    # 2) OTLP bridge fallback (vendor-neutral; user/thread as metadata only).
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if not endpoint:
        logger.warning("TRACING_ENABLED but no LANGFUSE_* keys and no OTEL_EXPORTER_OTLP_ENDPOINT — tracing off")
        return False
    try:  # the OTLP HTTP exporter + SDK (langsmith[otel])
        import opentelemetry.exporter.otlp.proto.http.trace_exporter  # noqa: F401
        import opentelemetry.sdk.trace  # noqa: F401
    except Exception as e:  # pragma: no cover
        logger.warning("TRACING_ENABLED but OpenTelemetry packages missing (%s) — tracing off", e)
        return False
    os.environ.setdefault("LANGSMITH_TRACING", "true")
    os.environ.setdefault("LANGSMITH_OTEL_ENABLED", "true")
    os.environ.setdefault("OTEL_SERVICE_NAME", getattr(settings, "otel_service_name", "joyjoy-backend"))
    # langsmith's tracer wants an API key present even in OTLP mode (the OTLP auth
    # comes from OTEL_EXPORTER_OTLP_HEADERS, so a placeholder is harmless).
    os.environ.setdefault("LANGSMITH_API_KEY", "otlp-noop")
    logger.info("tracing enabled → OTLP %s (service=%s)", endpoint, os.environ.get("OTEL_SERVICE_NAME"))
    return True


def langchain_callbacks(model: str) -> list:
    """Callbacks attached to each agent run: the Prometheus handler (no-op when
    metrics off) + the Langfuse handler when tracing via the native callback."""
    cbs: list = [PrometheusCallbackHandler(model)]
    if _LANGFUSE_HANDLER is not None:
        cbs.append(_LANGFUSE_HANDLER)
    return cbs


# ── HTTP request metrics (pure-ASGI; won't buffer SSE like BaseHTTPMiddleware) ──
_ID_SEG = re.compile(r"^(run-|ap-|t-)?[0-9a-f]{8,}$|^\d+$", re.I)


def _norm_path(scope) -> str:
    """Templated request path for low-cardinality labels: prefer the matched route
    template, else collapse id-like segments (hex/uuid/run-/ap-/numeric) to ':id'."""
    route = scope.get("route")
    p = getattr(route, "path", None) or getattr(route, "path_format", None)
    if p:
        return p
    raw = scope.get("path", "/") or "/"
    return "/".join(":id" if _ID_SEG.match(seg) else seg for seg in raw.split("/")) or "/"


class RequestMetricsMiddleware:
    """Times each HTTP request and records count + latency by method/path/status.
    Pure ASGI so streaming responses (SSE runs) pass through untouched."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or not _M:
            await self.app(scope, receive, send)
            return
        method = scope.get("method", "-")
        start = time.monotonic()
        status = {"code": 500}

        async def _send(message):
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, _send)
        finally:
            path = _norm_path(scope)
            _M["http_requests"].labels(method, path, str(status["code"])).inc()
            _M["http_seconds"].labels(method, path).observe(time.monotonic() - start)


def trace_config(ctx, model: str) -> dict:
    """Trace metadata/tags/run_name merged into the agent run config so spans are
    attributed PER-USER and PER-SESSION. The ``langfuse_*`` keys are recognized by
    the Langfuse LangChain handler and map to its native User + Session fields:
      * langfuse_user_id   → the tenant (one user → many sessions)
      * langfuse_session_id→ the conversation/thread (the session label) → groups all
                             turns of a chat and powers session view/replay.
    The joyjoy.* duplicates remain as generic metadata (also readable via OTLP)."""
    user_id = getattr(ctx, "user_id", None)
    thread_id = getattr(ctx, "thread_id", None)
    return {
        "run_name": "joyjoy.agent",
        "tags": [f"model:{model}"],
        "metadata": {
            # Native Langfuse user/session attribution.
            "langfuse_user_id": user_id,
            "langfuse_session_id": thread_id,
            "langfuse_tags": [f"model:{model}"],
            # Generic duplicates (filterable, and carried over the OTLP fallback).
            "joyjoy.user_id": user_id,
            "joyjoy.thread_id": thread_id,
            "joyjoy.model": model,
        },
    }
