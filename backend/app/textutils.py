"""Small, dependency-free text/path helpers shared across modules.

Lives on its own so the same logic isn't re-implemented per concern (the
workspace-segment sanitizer was previously copy-pasted in agent.py and
workspace.py; the KV/line parsers were private to mcp_runtime)."""

from __future__ import annotations

import re

_SEGMENT_RE = re.compile(r"[^A-Za-z0-9._-]")


def safe_segment(value, max_len: int = 128) -> str:
    """Sanitize a value into a single safe path segment (used for workspace /
    session ids). Non-``[A-Za-z0-9._-]`` chars become ``_``; capped at ``max_len``.
    May return ``""`` — callers apply their own fallback (``"default"`` / ``None``)."""
    return _SEGMENT_RE.sub("_", str(value or ""))[:max_len]


def split_lines(text: str | None) -> list[str]:
    """Non-empty, stripped lines of ``text`` (e.g. an args textarea)."""
    return [ln.strip() for ln in (text or "").splitlines() if ln.strip()]


def parse_kv(text: str | None) -> dict[str, str]:
    """Parse ``KEY=value`` lines (env / headers textareas) into a dict."""
    out: dict[str, str] = {}
    for ln in (text or "").splitlines():
        ln = ln.strip()
        if not ln or "=" not in ln:
            continue
        k, _sep, v = ln.partition("=")
        if k.strip():
            out[k.strip()] = v.strip()
    return out
