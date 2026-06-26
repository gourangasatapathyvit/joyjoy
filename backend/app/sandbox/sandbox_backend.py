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
from opensandbox.models.filesystem import WriteEntry

from app.sandbox import sandbox as sandbox_mgr
from app.core.config import Settings
from app.core.constants import DEFAULT_USER_ID, FILE_READ_DEFAULT_LIMIT

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
        self.user_id = str(user_id or DEFAULT_USER_ID)
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
    def _mount(self) -> str:
        return self.settings.sandbox_mount_path.rstrip("/") or "/workspace"

    def _w(self, path: str) -> str:
        """Map an agent file path into the durable volume mount. The deepagents file
        tools use root-relative paths (e.g. ``/data.txt``); those must land under the
        mounted volume (``/workspace``) or they'd hit the container's ephemeral layer
        (lost on restart, invisible to the dock). Paths already under the mount pass
        through unchanged."""
        mount = self._mount
        if not path:
            return mount
        if path == mount or path.startswith(mount + "/"):
            return path
        return f"{mount}{path}" if path.startswith("/") else f"{mount}/{path}"

    @property
    def id(self) -> str:
        return self._sb().id

    # File ops: remap the agent path into the volume, then reuse BaseSandbox's logic.
    def ls(self, path: str):
        return super().ls(self._w(path))

    def read(self, file_path: str, offset: int = 0, limit: int = FILE_READ_DEFAULT_LIMIT):
        return super().read(self._w(file_path), offset, limit)

    def write(self, file_path: str, content: str):
        return super().write(self._w(file_path), content)

    def edit(self, file_path: str, old_string: str, new_string: str, replace_all: bool = False):  # noqa: FBT001, FBT002
        return super().edit(self._w(file_path), old_string, new_string, replace_all)

    def glob(self, pattern: str, path: str | None = None):
        return super().glob(pattern, self._w(path) if path else self._mount)

    def grep(self, pattern: str, path: str | None = None, glob: str | None = None):
        return super().grep(pattern, self._w(path) if path else self._mount, glob)

    # The agent runs ASYNC, so deepagents calls the a* methods — which in BaseSandbox
    # route to aupload_files/aexecute with the RAW agent path and BYPASS the sync
    # overrides above. Without these, write_file("/x") lands in the container's
    # ephemeral root instead of the /workspace volume (lost + invisible to the dock).
    # Mirror the sync remapping so every path lands under the mount. (_w is idempotent.)
    async def als(self, path: str):
        return await super().als(self._w(path))

    async def aread(self, file_path: str, offset: int = 0, limit: int = FILE_READ_DEFAULT_LIMIT):
        return await super().aread(self._w(file_path), offset, limit)

    async def awrite(self, file_path: str, content: str):
        return await super().awrite(self._w(file_path), content)

    async def aedit(self, file_path: str, old_string: str, new_string: str, replace_all: bool = False):  # noqa: FBT001, FBT002
        return await super().aedit(self._w(file_path), old_string, new_string, replace_all)

    async def aglob(self, pattern: str, path: str | None = None):
        return await super().aglob(pattern, self._w(path) if path else self._mount)

    async def agrep(self, pattern: str, path: str | None = None, glob: str | None = None):
        return await super().agrep(pattern, self._w(path) if path else self._mount, glob)

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        sb = self._sb()
        # Run with the volume as cwd so relative paths + the agent's working dir
        # resolve inside the durable workspace.
        wrapped = f"cd {self._mount} 2>/dev/null; {command}"
        execution = sandbox_mgr.run_sync(sb.commands.run(wrapped))
        return ExecuteResponse(
            output=_combined_output(execution),
            exit_code=getattr(execution, "exit_code", None),
        )

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
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
