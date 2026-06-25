"""Unit tests for the agent system prompt — specifically the ``MEDIA:`` inline-render
contract.

The frontend only shows a file inline when the assistant emits a ``MEDIA:<path>``
line (``lib/media.splitMediaMarkers`` lifts it into a media part → ``/v1/media``).
If the prompt stops instructing the agent to use that marker, "render this here"
silently regresses to the agent pasting raw SVG/base64 text. These tests guard the
contract at both the constant and the assembled-prompt level.
"""

from __future__ import annotations

from app.agent.agent import _system_prompt_for
from app.core.config import Settings
from app.agent.prompts import DEFAULT_SYSTEM_PROMPT, SANDBOX_PROMPT_SUFFIX


def test_core_prompt_declares_media_contract():
    # The marker the renderer keys off must be taught in the core prompt...
    assert "MEDIA:" in DEFAULT_SYSTEM_PROMPT
    # ...along with the negative instruction (don't paste raw bytes/markup instead).
    low = DEFAULT_SYSTEM_PROMPT.lower()
    assert "do not paste" in low or "never paste" in low


def test_sandbox_suffix_has_media_example_with_mount():
    rendered = SANDBOX_PROMPT_SUFFIX.format(mount="/workspace")
    assert "MEDIA:/workspace/" in rendered  # concrete, mount-qualified example
    assert "{mount}" not in rendered  # every format placeholder substituted


async def test_system_prompt_includes_media_contract_without_sandbox():
    prompt = await _system_prompt_for("u1", Settings(sandbox_enabled=False))
    assert "MEDIA:" in prompt  # core contract present even with no sandbox


async def test_system_prompt_includes_media_contract_with_sandbox():
    prompt = await _system_prompt_for(
        "u1", Settings(sandbox_enabled=True, sandbox_mount_path="/workspace")
    )
    assert "MEDIA:" in prompt
    assert "MEDIA:/workspace/" in prompt  # sandbox example, mount substituted
    assert "{mount}" not in prompt  # no leftover format placeholders


async def test_sandbox_prompt_is_superset_of_plain():
    plain = await _system_prompt_for("u1", Settings(sandbox_enabled=False))
    sandboxed = await _system_prompt_for(
        "u1", Settings(sandbox_enabled=True, sandbox_mount_path="/workspace")
    )
    assert sandboxed.startswith(plain.rstrip()) or len(sandboxed) > len(plain)
