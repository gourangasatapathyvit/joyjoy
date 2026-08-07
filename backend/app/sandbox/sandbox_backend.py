"""Deepagents backend backed by a per-USER OpenSandbox sandbox, shared across all
of that user's threads. Each thread gets its own subdirectory inside the shared
volume, isolated from sibling threads by a dedicated unprivileged Linux user +
``chmod 700`` (``sandbox.ensure_thread_workspace*``) — not by which container it
got. ``execute()`` always runs as that thread's own uid, which is also what makes
``ls``/``read``/``edit``/``glob``/``grep`` OS-isolated for free: ``BaseSandbox``
implements all of them as shell scripts piped through ``execute()``.

Subclasses ``BaseSandbox`` and implements only the sync primitives it requires —
``execute`` / ``upload_files`` / ``download_files`` / ``id`` — by bridging to the
async OpenSandbox SDK on the dedicated sandbox loop (see ``sandbox.run_sync``).

The target THREAD segment is resolved PER OPERATION from the runtime context
(same mechanism as the host SessionFilesystemBackend); the target USER — and
therefore which container — is fixed at construction time (``build_backend`` is
already called per-user), so one cached backend instance per (user, model) still
serves every thread of that user.
"""

from __future__ import annotations

import logging

from deepagents.backends.sandbox import BaseSandbox
from deepagents.backends.protocol import (
    DeleteResult,
    EditResult,
    ExecuteResponse,
    FileDownloadResponse,
    FileUploadResponse,
    GlobResult,
    GrepResult,
    LsResult,
    ReadResult,
    WriteResult,
)
from opensandbox.models.execd import RunCommandOpts
from opensandbox.models.filesystem import WriteEntry

from app.sandbox import sandbox as sandbox_mgr
from app.sandbox.confine import confine
from app.core.config import Settings
from app.core.constants import DEFAULT_USER_ID, FILE_READ_DEFAULT_LIMIT

logger = logging.getLogger("joyjoy.sandbox")


class _ConfinementError(Exception):
    """Raised when a path would resolve outside the current thread's subfolder."""


def _combined_output(execution) -> str:
    logs = getattr(execution, "logs", None)
    if logs is None:
        return getattr(execution, "text", "") or ""
    parts = [getattr(s, "text", "") for s in (getattr(logs, "stdout", None) or [])]
    parts += [getattr(s, "text", "") for s in (getattr(logs, "stderr", None) or [])]
    return "\n".join(p for p in parts if p is not None)


class OpenSandboxBackend(BaseSandbox):
    """Per-user sandbox backend. ``seg_fn`` resolves the current thread/workspace
    segment from the runtime context (injected by agent.build_backend to avoid an
    import cycle); ``workspace_id`` overrides it (tests / explicit use)."""

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
        """The current THREAD/workspace segment (subfolder + uid derivation) —
        distinct from ``self.user_id``, which selects the shared container."""
        if self._workspace_id:
            return self._workspace_id
        seg = self._seg_fn() if self._seg_fn else None
        return seg or "default"

    def _sb(self):
        sb, _sid = sandbox_mgr.acquire_sync(self.settings, self.user_id)
        return sb

    @property
    def _mount(self) -> str:
        return self.settings.sandbox_mount_path.rstrip("/") or "/workspace"

    def _thread(self) -> tuple[str, int]:
        """(abs_thread_dir, uid) for the current thread — bootstraps the thread's
        subfolder + dedicated OS user on first use, cached thereafter."""
        return sandbox_mgr.ensure_thread_workspace_sync(self.settings, self.user_id, self._seg())

    def _w(self, path: str) -> str:
        """Map an agent file path into the CURRENT THREAD's confined subfolder,
        rejecting any ``..``/absolute-path escape attempt (raises
        ``_ConfinementError``). The deepagents file tools use root-relative paths
        (e.g. ``/data.txt``); those land under ``{mount}/{thread_seg}``, never the
        shared user mount directly, so one thread can't read/write another's
        files even in this shared-per-user container."""
        thread_root, _uid = self._thread()
        full = confine(thread_root, path or "/")
        if full is None:
            raise _ConfinementError(path)
        return full

    @property
    def id(self) -> str:
        return self._sb().id

    # File ops: remap the agent path into the thread's subfolder, then reuse
    # BaseSandbox's logic. A confinement escape returns a clean tool error
    # instead of raising, matching how BaseSandbox reports other failures.
    def ls(self, path: str):
        try:
            wp = self._w(path)
        except _ConfinementError:
            return LsResult(error="path escapes the session workspace")
        return super().ls(wp)

    def read(self, file_path: str, offset: int = 0, limit: int = FILE_READ_DEFAULT_LIMIT):
        try:
            wp = self._w(file_path)
        except _ConfinementError:
            return ReadResult(error="path escapes the session workspace")
        return super().read(wp, offset, limit)

    def write(self, file_path: str, content: str):
        try:
            wp = self._w(file_path)
        except _ConfinementError:
            return WriteResult(error="path escapes the session workspace")
        return super().write(wp, content)

    def edit(self, file_path: str, old_string: str, new_string: str, replace_all: bool = False):  # noqa: FBT001, FBT002
        try:
            wp = self._w(file_path)
        except _ConfinementError:
            return EditResult(error="path escapes the session workspace")
        return super().edit(wp, old_string, new_string, replace_all)

    def delete(self, file_path: str):
        # No adelete() override needed: BackendProtocol's default adelete()
        # dispatches to asyncio.to_thread(self.delete, ...), and BaseSandbox
        # (unlike ls/read/write/edit/glob/grep) doesn't shadow it with its own
        # async-native implementation — so this confinement check already
        # covers both the sync and async delete tool calls.
        try:
            wp = self._w(file_path)
        except _ConfinementError:
            return DeleteResult(error="path escapes the session workspace")
        return super().delete(wp)

    def glob(self, pattern: str, path: str | None = None):
        try:
            wp = self._w(path) if path else self._thread()[0]
        except _ConfinementError:
            return GlobResult(error="path escapes the session workspace")
        return super().glob(pattern, wp)

    def grep(self, pattern: str, path: str | None = None, glob: str | None = None):
        try:
            wp = self._w(path) if path else self._thread()[0]
        except _ConfinementError:
            return GrepResult(error="path escapes the session workspace")
        return super().grep(pattern, wp, glob)

    # The agent runs ASYNC, so deepagents calls the a* methods — which in BaseSandbox
    # route to aupload_files/aexecute with the RAW agent path and BYPASS the sync
    # overrides above. Mirror the sync remapping so every path lands under the
    # thread's confined subfolder. (_w is idempotent.)
    async def als(self, path: str):
        try:
            wp = self._w(path)
        except _ConfinementError:
            return LsResult(error="path escapes the session workspace")
        return await super().als(wp)

    async def aread(self, file_path: str, offset: int = 0, limit: int = FILE_READ_DEFAULT_LIMIT):
        try:
            wp = self._w(file_path)
        except _ConfinementError:
            return ReadResult(error="path escapes the session workspace")
        return await super().aread(wp, offset, limit)

    async def awrite(self, file_path: str, content: str):
        try:
            wp = self._w(file_path)
        except _ConfinementError:
            return WriteResult(error="path escapes the session workspace")
        return await super().awrite(wp, content)

    async def aedit(self, file_path: str, old_string: str, new_string: str, replace_all: bool = False):  # noqa: FBT001, FBT002
        try:
            wp = self._w(file_path)
        except _ConfinementError:
            return EditResult(error="path escapes the session workspace")
        return await super().aedit(wp, old_string, new_string, replace_all)

    async def aglob(self, pattern: str, path: str | None = None):
        try:
            wp = self._w(path) if path else self._thread()[0]
        except _ConfinementError:
            return GlobResult(error="path escapes the session workspace")
        return await super().aglob(pattern, wp)

    async def agrep(self, pattern: str, path: str | None = None, glob: str | None = None):
        try:
            wp = self._w(path) if path else self._thread()[0]
        except _ConfinementError:
            return GrepResult(error="path escapes the session workspace")
        return await super().agrep(pattern, wp, glob)

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        sb = self._sb()
        thread_root, uid = self._thread()
        # Run scoped to the thread's OWN uid + its own subfolder as cwd — this is
        # the real enforcement layer: a shell trick like `cd ../other-thread &&
        # cat secret` still hits a kernel EACCES, because that sibling directory
        # is chmod 700 and owned by a DIFFERENT uid. ls/read/edit/glob/grep are
        # all implemented by BaseSandbox as scripts run through this same
        # execute(), so they inherit this isolation for free.
        execution = sandbox_mgr.run_sync(
            sb.commands.run(command, opts=RunCommandOpts(working_directory=thread_root, uid=uid)),
        )
        return ExecuteResponse(
            output=_combined_output(execution),
            exit_code=getattr(execution, "exit_code", None),
        )

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        # No confine() here: by the time write()/edit()/awrite()/aedit() reach this
        # (their only caller for real workspace paths), the path already went
        # through _w() above. The other caller — BaseSandbox's large-payload edit
        # fallback — uploads its OWN framework-internal /tmp temp files here
        # directly (never agent-controlled, never under the thread subfolder by
        # design), which confining against thread_root would break.
        sb = self._sb()
        entries = [WriteEntry(path=path, data=content) for path, content in files]
        try:
            sandbox_mgr.run_sync(sb.files.write_files(entries))
        except Exception as e:  # noqa: BLE001 - partial-success contract: error per file
            return [FileUploadResponse(path=path, error=str(e)) for path, _ in files]
        return [FileUploadResponse(path=path) for path, _ in files]

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        sb = self._sb()
        thread_root, _uid = self._thread()
        out: list[FileDownloadResponse] = []
        for p in paths:
            full = confine(thread_root, p)
            if full is None:
                out.append(FileDownloadResponse(path=p, error="path escapes the session workspace"))
                continue
            try:
                data = sandbox_mgr.run_sync(sb.files.read_bytes(full))
                out.append(FileDownloadResponse(path=p, content=bytes(data)))
            except Exception as e:  # noqa: BLE001
                out.append(FileDownloadResponse(path=p, error=str(e)))
        return out
