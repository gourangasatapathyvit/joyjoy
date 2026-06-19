"""Per-request runtime context.

Passed to the deep agent as ``context=`` at invoke time, and read back by the
``StoreBackend`` namespace factory to scope every storage operation to the
calling user. This is the single source of truth for multi-tenant isolation.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AgentContext:
    user_id: str
    thread_id: str | None = None
    is_admin: bool = False
