"""Centralized operational limits shared across the backend.

Deployment / environment-driven configuration lives in ``config.Settings``
(env-overridable). This module is the single home for the *fixed* app-level
limits — byte caps, timeouts, list bounds — that were previously duplicated as
ad-hoc ``_CONST`` definitions scattered across modules (and, in one case, the
same name ``_MAX_BYTES`` meaning two different things in two files). Grouping
them here mirrors the frontend's ``src/lib/constants.ts``.
"""

from __future__ import annotations

MB = 1024 * 1024

# Compiled-agent LRU cache bound (agent_common.cache_put evicts past this).
AGENT_CACHE_MAX = 128

# Seconds to wait when probing one MCP server's tool list — one slow/dead server
# must not hang the agent build or the MCP tab (mcp_runtime).
MCP_PROBE_TIMEOUT_S = 10

# Max dynamic /memories/ files returned in one list call (memory_store).
MEMORIES_LIST_LIMIT = 1000

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
