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

# TTL (seconds) for the per-user blob cache (merged model specs + loaded MCP tools)
# in agent_common. Cleared eagerly on any per-user CRUD write; this bounds staleness
# for changes that bypass that path (e.g. global-seed edits) while still removing the
# repeated remote-DB reads / MCP stdio spawns from the hot agent-build path.
USER_BLOB_TTL_S = 60.0
# Hard cap on total entries in the per-user blob cache (LRU-evicted past this) so a
# long-lived process serving many users can't grow without bound. ~2 blobs/user.
USER_BLOB_CACHE_MAX = 512
# Fractional jitter applied to every cache TTL (±) so entries created together don't
# all expire in the same instant (avoids a synchronized refill / thundering herd).
CACHE_TTL_JITTER = 0.15

# TTL (seconds) for the read-only GLOBAL skills manifest cache (dbfs.DbSkillsBackend).
# The deepagents SkillsMiddleware re-lists + downloads every skill's SKILL.md on each
# turn; without this that's an N+1 of remote-DB round-trips per message. Global skills
# don't change at runtime (the UI rejects global edits), so a TTL alone is safe; the
# per-user manifest rides the user-blob cache and is cleared on user-skill CRUD.
GLOBAL_SKILL_MANIFEST_TTL_S = 300.0

# ---- timeouts (seconds) ----
# Seconds to wait when probing one MCP server's tool list — one slow/dead server
# must not hang the agent build or the MCP tab (mcp_runtime).
MCP_PROBE_TIMEOUT_S = 10
MODEL_PROBE_TIMEOUT_S = 45  # standard completion health probe (agent.test_model)
REASONING_PROBE_TIMEOUT_S = 60  # reasoning/thinking capability probe (agent.test_model)
OFFICE_TO_PDF_TIMEOUT_S = 90  # headless LibreOffice office→pdf conversion (media)
SMTP_TIMEOUT_S = 20  # SMTP connect/send for the password-reset OTP email (users)

# ---- Postgres connection resilience (persistence pool + SQLAlchemy engine) ----
# libpq connect params for a REMOTE Postgres behind a firewall/NAT: turn a silently
# dropped connection into a fast, detectable error instead of a ~13-min kernel-
# retransmit hang (tcp_retries2). psycopg accepts these as connect kwargs, so both
# the langgraph pool and the SQLAlchemy engine share this one dict. Seconds, except
# tcp_user_timeout (milliseconds).
PG_KEEPALIVE_ARGS = {
    "keepalives": 1,
    "keepalives_idle": 30,
    "keepalives_interval": 10,
    "keepalives_count": 3,
    "tcp_user_timeout": 15000,  # fail a stuck send after ~15s, not ~13 min
    "connect_timeout": 10,
}
PG_POOL_MAX_IDLE_S = 120.0  # recycle a pooled conn idle longer than this (before a NAT reaps it)
PG_POOL_MAX_LIFETIME_S = 1800.0  # hard cap on any pooled conn's age (also the engine pool_recycle)

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
MAX_DOWNLOAD_BYTES = 200 * MB  # cap for a workspace file/folder-zip download (workspace)
MAX_MEDIA_BYTES = 25_000_000  # largest file /v1/media will serve (media)
MAX_MEDIA_B64_BYTES = 8_000_000  # skip embedding a base64 block bigger than this inline (media)
MAX_WORKSPACE_PREVIEW_BYTES = 1_000_000  # text-preview cap for the workspace file viewer (workspace)

# ---- per-user skill upload caps (skills_store.import_user_skill) ----
MAX_SKILL_FILES = 300
MAX_SKILL_FILE_BYTES = 5 * MB
MAX_SKILL_TOTAL_BYTES = 30 * MB
