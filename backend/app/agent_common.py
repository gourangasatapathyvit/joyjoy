"""Shared low-level helpers for the agent subsystem.

Holds the compiled-agent cache + a couple of tiny validators that the agent
factory and the CRUD modules (providers/mcp/skills/memory) all need. Lives in
its own module so those modules can import it WITHOUT a circular dependency on
``agent.py`` (which itself imports from them)."""

from __future__ import annotations

import logging

from .constants import AGENT_CACHE_MAX, DEFAULT_USER_ID

logger = logging.getLogger("joyjoy.agent")

# (kind, user_id, model_id, reasoning) -> compiled deep agent. Bounded so a
# many-user / many-model process doesn't grow the cache without limit; the
# oldest entry is evicted past the cap (agents are cheap to rebuild on demand).
_AGENT_CACHE: dict[tuple, object] = {}


def cache_put(key: tuple, agent: object) -> None:
    if len(_AGENT_CACHE) >= AGENT_CACHE_MAX:  # evict oldest (insertion order)
        _AGENT_CACHE.pop(next(iter(_AGENT_CACHE)), None)
    _AGENT_CACHE[key] = agent


def invalidate_user_cache(user_id: str) -> None:
    """Drop cached agents for a user so skill/MCP/memory edits take effect next call."""
    uid = str(user_id or DEFAULT_USER_ID)
    for k in [k for k in _AGENT_CACHE if isinstance(k, tuple) and len(k) >= 2 and k[1] == uid]:
        _AGENT_CACHE.pop(k, None)


def valid_name(name: str) -> bool:
    """A safe skill/model/server name: non-empty, no path separators, no traversal."""
    return bool(name) and not any(c in name for c in ("/", "\\")) and ".." not in name
