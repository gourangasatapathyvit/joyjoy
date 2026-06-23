"""Deepagents backend backed by a per-(user,thread) OpenSandbox sandbox.

Subclasses ``BaseSandbox`` and implements only the sync primitives it requires —
``execute`` / ``upload_files`` / ``download_files`` / ``id`` — by bridging to the
async OpenSandbox SDK on the dedicated sandbox loop (see ``sandbox.run_sync``).
``BaseSandbox`` derives ls/read/edit/glob/grep from those via shell commands, so
the agent's file CRUD *and* code execution both happen inside the sandbox.

The target sandbox is resolved PER OPERATION from the runtime context (the
session's ``workspace_id`` — same mechanism as the host SessionFilesystemBackend),
so one cached backend instance per (user, model) still serves every thread.
"""

from __future__ import annotations

import logging

from deepagents.backends.sandbox import BaseSandbox
from deepagents.backends.protocol import (
    ExecuteResponse,
    FileDownloadResponse,
    FileUploadResponse,
)

from . import sandbox as sandbox_mgr
from .config import Settings

logger = logging.getLogger("joyjoy.sandbox")


def _combined_output(execution) -> str:
    logs = getattr(execution, "logs", None)
    if logs is None:
        return getattr(execution, "text", "") or ""
    parts = [getattr(s, "text", "") for s in (getattr(logs, "stdout", None) or [])]
    parts += [getattr(s, "text", "") for s in (getattr(logs, "stderr", None) or [])]
    return "\n".join(p for p in parts if p is not None)


class OpenSandboxBackend(BaseSandbox):
    """Per-session sandbox backend. ``seg_fn`` resolves the current workspace_id from
    the runtime context (injected by agent.build_backend to avoid an import cycle);
    ``workspace_id`` overrides it (tests / explicit use)."""

    def __init__(
        self,
        settings: Settings,
        user_id: str,
        *,
        seg_fn=None,
        workspace_id: str | None = None,
    ):
        self.settings = settings
        self.user_id = str(user_id or "default")
        self._seg_fn = seg_fn
        self._workspace_id = workspace_id

    def _seg(self) -> str:
        if self._workspace_id:
            return self._workspace_id
        seg = self._seg_fn() if self._seg_fn else None
        return seg or "default"

    def _sb(self):
        sb, _sid = sandbox_mgr.acquire_sync(self.settings, self._seg())
        return sb

    @property
    def id(self) -> str:
        return self._sb().id

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        sb = self._sb()
        execution = sandbox_mgr.run_sync(sb.commands.run(command))
        return ExecuteResponse(
            output=_combined_output(execution),
            exit_code=getattr(execution, "exit_code", None),
        )

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        from opensandbox.models.filesystem import WriteEntry

        sb = self._sb()
        entries = [WriteEntry(path=path, data=content) for path, content in files]
        try:
            sandbox_mgr.run_sync(sb.files.write_files(entries))
        except Exception as e:  # noqa: BLE001 - partial-success contract: error per file
            return [FileUploadResponse(path=path, error=str(e)) for path, _ in files]
        return [FileUploadResponse(path=path) for path, _ in files]

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        sb = self._sb()
        out: list[FileDownloadResponse] = []
        for p in paths:
            try:
                data = sandbox_mgr.run_sync(sb.files.read_bytes(p))
                out.append(FileDownloadResponse(path=p, content=bytes(data)))
            except Exception as e:  # noqa: BLE001
                out.append(FileDownloadResponse(path=p, error=str(e)))
        return out
