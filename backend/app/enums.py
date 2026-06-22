"""Shared string enums for the backend.

``StrEnum`` members ARE their string value, so they serialize to JSON as the
plain string, compare equal to the raw literal, and work as dict keys / in
``in`` checks — callers can treat them exactly like the strings they replace,
but with one authoritative definition instead of literals scattered across
modules.
"""

from __future__ import annotations

from enum import StrEnum

# Non-canonical provider spellings (UI / SDK synonyms) -> canonical value.
_PROVIDER_ALIASES = {"google": "gemini", "openai_compatible": "openai"}


class Provider(StrEnum):
    """Model providers ``build_model_for`` dispatches on (and the seeded
    ``global_providers`` rows). Canonical ids only — synonyms resolve via
    :meth:`coerce`."""

    AZURE_OPENAI = "azure_openai"
    ANTHROPIC = "anthropic"
    BEDROCK = "bedrock"
    OPENAI = "openai"
    GEMINI = "gemini"

    @classmethod
    def coerce(cls, value, default: "Provider | None" = None) -> "Provider":
        """Best-effort parse of a raw provider string (case-insensitive, synonyms
        resolved) into a canonical :class:`Provider`; falls back to ``default``
        (or ``AZURE_OPENAI``) when unknown."""
        s = str(value or "").strip().lower()
        s = _PROVIDER_ALIASES.get(s, s)
        try:
            return cls(s)
        except ValueError:
            return default or cls.AZURE_OPENAI


class McpStatus(StrEnum):
    """Lifecycle status of an MCP server as reported to the UI."""

    CONFIGURED = "configured"  # known but not yet probed
    ACTIVE = "active"  # connected; tools loaded
    INVALID_CONFIG = "invalid_config"  # unreachable / failed to probe
    DISABLED = "disabled"  # turned off by the user
