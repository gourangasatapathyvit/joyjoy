"""Shared low-level helpers for the agent subsystem.

Holds the compiled-agent cache + a couple of tiny validators that the agent
factory and the CRUD modules (providers/mcp/skills/memory) all need. Lives in
its own module so those modules can import it WITHOUT a circular dependency on
``agent.py`` (which itself imports from them)."""

from __future__ import annotations

import logging
from collections import OrderedDict

from app.core.constants import AGENT_CACHE_MAX, DEFAULT_USER_ID

logger = logging.getLogger("joyjoy.agent")

# (kind, user_id, model_id, reasoning) -> compiled deep agent. A bounded LRU:
# an OrderedDict ordered most-recently-used last. ``cache_get`` promotes on hit
# and ``cache_put`` evicts the least-recently-used (front) past the cap — so a
# hot agent (e.g. the default model) is NOT evicted just for being created first
# (a plain insertion-order dict would do that). Agents are cheap to rebuild.
_AGENT_CACHE: OrderedDict[tuple, object] = OrderedDict()


def cache_get(key: tuple) -> object | None:
    """Fetch + mark as most-recently-used (the LRU promotion). None if absent."""
    agent = _AGENT_CACHE.get(key)
    if agent is not None:
        _AGENT_CACHE.move_to_end(key)
    return agent


def cache_put(key: tuple, agent: object) -> None:
    _AGENT_CACHE[key] = agent
    _AGENT_CACHE.move_to_end(key)  # newest = most-recently-used (last)
    while len(_AGENT_CACHE) > AGENT_CACHE_MAX:
        _AGENT_CACHE.popitem(last=False)  # evict the least-recently-used (front)


def invalidate_user_cache(user_id: str) -> None:
    """Drop cached agents for a user so skill/MCP/memory edits take effect next call."""
    uid = str(user_id or DEFAULT_USER_ID)
    for k in [k for k in _AGENT_CACHE if isinstance(k, tuple) and len(k) >= 2 and k[1] == uid]:
        _AGENT_CACHE.pop(k, None)


def valid_name(name: str) -> bool:
    """A safe skill/model/server name: non-empty, no path separators, no traversal."""
    return bool(name) and not any(c in name for c in ("/", "\\")) and ".." not in name
