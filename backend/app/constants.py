"""Centralized operational limits shared across the backend.

Deployment / environment-driven configuration lives in ``config.Settings``
(env-overridable). This module is the single home for the *fixed* app-level
limits — byte caps, timeouts, list bounds — that were previously duplicated as
ad-hoc ``_CONST`` definitions scattered across modules (and, in one case, the
same name ``_MAX_BYTES`` meaning two different things in two files). Grouping
them here mirrors the frontend's ``src/lib/constants.ts``.
"""

from __future__ import annotations

# Fallback tenant bucket when no user id is resolved (dev / no-auth paths). The
# real per-user identity is the auth-resolved uuid; this is only the "no user yet"
# sentinel that the per-user stores/backends key off.
DEFAULT_USER_ID = "default"

MB = 1024 * 1024

# Compiled-agent LRU cache bound (agent_common.cache_put evicts past this).
AGENT_CACHE_MAX = 128

# ---- timeouts (seconds) ----
# Seconds to wait when probing one MCP server's tool list — one slow/dead server
# must not hang the agent build or the MCP tab (mcp_runtime).
MCP_PROBE_TIMEOUT_S = 10
MODEL_PROBE_TIMEOUT_S = 45  # standard completion health probe (agent.test_model)
REASONING_PROBE_TIMEOUT_S = 60  # reasoning/thinking capability probe (agent.test_model)
OFFICE_TO_PDF_TIMEOUT_S = 90  # headless LibreOffice office→pdf conversion (media)
SMTP_TIMEOUT_S = 20  # SMTP connect/send for the password-reset OTP email (users)

# ---- list / read bounds ----
# Max dynamic /memories/ files returned in one list call (memory_store).
MEMORIES_LIST_LIMIT = 1000
SESSIONS_LIST_LIMIT = 200  # max sessions returned by list_sessions (sessions)
FILE_READ_DEFAULT_LIMIT = 2000  # default max lines per file read (dbfs / sandbox backends)

# ---- model token budgets (agent.build_model_for) ----
DEFAULT_MAX_TOKENS = 4096  # fallback completion budget when a model spec sets none
REASONING_BUDGET_OVERHEAD = 1024  # headroom added above a model's thinking budget
# Per-effort thinking-token budgets (anthropic extended thinking).
REASONING_BUDGETS = {"minimal": 1024, "low": 2048, "medium": 4096, "high": 8192, "extra_high": 16384}

# Password-reset OTP attempts allowed before the code is invalidated (users).
OTP_MAX_ATTEMPTS = 5

# ---- byte caps ----
MAX_UPLOAD_BYTES = 25 * MB  # a single workspace upload (main)
MAX_MEDIA_BYTES = 25_000_000  # largest file /v1/media will serve (media)
MAX_MEDIA_B64_BYTES = 8_000_000  # skip embedding a base64 block bigger than this inline (media)
MAX_WORKSPACE_PREVIEW_BYTES = 1_000_000  # text-preview cap for the workspace file viewer (workspace)

# ---- per-user skill upload caps (skills_store.import_user_skill) ----
MAX_SKILL_FILES = 300
MAX_SKILL_FILE_BYTES = 5 * MB
MAX_SKILL_TOTAL_BYTES = 30 * MB
