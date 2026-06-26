"""Shared low-level helpers for the agent subsystem.

Holds the compiled-agent cache + a couple of tiny validators that the agent
factory and the CRUD modules (providers/mcp/skills/memory) all need. Lives in
its own module so those modules can import it WITHOUT a circular dependency on
``agent.py`` (which itself imports from them)."""

from __future__ import annotations

import logging
import random
import time
from collections import OrderedDict

from app.core.constants import (
    AGENT_CACHE_MAX,
    CACHE_TTL_JITTER,
    DEFAULT_USER_ID,
    USER_BLOB_CACHE_MAX,
    USER_BLOB_TTL_S,
)

logger = logging.getLogger("joyjoy.agent")


def jittered_ttl(ttl: float) -> float:
    """``ttl`` ± CACHE_TTL_JITTER so many entries created together don't expire in
    lockstep (avoids a synchronized cache refill). Shared by all app caches."""
    return ttl * (1.0 + random.uniform(-CACHE_TTL_JITTER, CACHE_TTL_JITTER))

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


_SPEC_BLOB = "model_specs"  # cached merged_model_specs result
_MCP_BLOB = "mcp_tools"  # cached load_mcp_tools result

# Per-user blob cache for the EXPENSIVE-to-recompute inputs of an agent build that
# don't depend on (model, reasoning): the merged model-spec catalog (several remote
# Postgres reads + secret decryption), the loaded MCP tool list (spawns stdio servers
# to enumerate), and the per-user skills manifest. Caching them cuts ~2s off every
# message and ~3s off cold builds.
#
# A BOUNDED LRU (OrderedDict, MRU last) keyed by (user_id, blob_name) with a jittered
# per-entry TTL: bounded so a long-lived process serving many users can't grow without
# limit (least-recently-used entries are evicted past USER_BLOB_CACHE_MAX); TTL is a
# staleness safety-net for changes that bypass invalidate_user_cache (e.g. global-seed
# edits). NOTE: values may hold decrypted secrets (model api_key) — this lives ONLY in
# process memory, never serialized to disk/redis, to preserve secrets-at-rest.
_USER_BLOBS: OrderedDict[tuple[str, str], tuple[float, object]] = OrderedDict()


def user_blob_get(user_id: str, name: str) -> object | None:
    """Return a cached, unexpired per-user value, or None if absent/stale."""
    key = (str(user_id or DEFAULT_USER_ID), name)
    ent = _USER_BLOBS.get(key)
    if ent is None:
        return None
    if ent[0] <= time.monotonic():  # expired
        _USER_BLOBS.pop(key, None)
        return None
    _USER_BLOBS.move_to_end(key)  # LRU promote on hit
    return ent[1]


def user_blob_put(user_id: str, name: str, value: object, ttl: float = USER_BLOB_TTL_S) -> None:
    key = (str(user_id or DEFAULT_USER_ID), name)
    _USER_BLOBS[key] = (time.monotonic() + jittered_ttl(ttl), value)
    _USER_BLOBS.move_to_end(key)  # newest = MRU (last)
    while len(_USER_BLOBS) > USER_BLOB_CACHE_MAX:
        _USER_BLOBS.popitem(last=False)  # evict the least-recently-used (front)


def invalidate_user_cache(user_id: str) -> None:
    """Drop cached agents + per-user blobs for a user so skill/MCP/memory/model edits
    take effect on the next call."""
    uid = str(user_id or DEFAULT_USER_ID)
    for k in [k for k in _AGENT_CACHE if isinstance(k, tuple) and len(k) >= 2 and k[1] == uid]:
        _AGENT_CACHE.pop(k, None)
    for k in [k for k in _USER_BLOBS if k[0] == uid]:
        _USER_BLOBS.pop(k, None)


def valid_name(name: str) -> bool:
    """A safe skill/model/server name: non-empty, no path separators, no traversal."""
    return bool(name) and not any(c in name for c in ("/", "\\")) and ".." not in name
