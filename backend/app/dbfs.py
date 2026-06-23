"""DB-backed deepagents backends — the bridge that lets the agent read/write its
``/memory/AGENTS.md`` and ``/skills/user/`` mounts straight against the relational
DB (``user_configs`` / ``user_skills`` / ``skill_files``) instead of the KV store.

These mount under ``CompositeBackend`` (see ``agent.build_backend``), which strips
the route prefix and calls the **async** methods (``als``/``aread``/``awrite``/
``aedit``/``adownload_files``) — so we override those directly with async DB I/O.
The sync methods are graceful no-ops/errors; the agent runs async and never hits
them. ``grep``/``glob`` return empty (these mounts aren't text-searched).
"""

from __future__ import annotations

import base64
import logging

from deepagents.backends.protocol import (
    BackendProtocol,
    EditResult,
    FileData,
    FileDownloadResponse,
    FileInfo,
    FileUploadResponse,
    GlobResult,
    GrepResult,
    LsResult,
    ReadResult,
    WriteResult,
)
from deepagents.backends import StoreBackend
from deepagents.backends.utils import (
    create_file_data,
    perform_string_replacement,
    slice_read_response,
)
from langgraph.config import get_store
from sqlalchemy import select

from .constants import DEFAULT_USER_ID
from .db import db_session, get_or_create_user_config
from .db.models import GlobalSkill, SkillFile, UserConfig, UserSkill

logger = logging.getLogger("joyjoy.dbfs")

# All dynamic memory files live in ONE store namespace (uid, "memories"); a
# disabled file carries enabled=False in its value (NOT a separate namespace —
# langgraph's sqlite store returns stale search results when the same key exists
# in two namespaces). This is the shared key/namespace contract.
MEMORIES_NS = "memories"


def memories_namespace(user_id) -> tuple[str, str]:
    return (str(user_id or DEFAULT_USER_ID), MEMORIES_NS)

# /memory/<file> -> UserConfig column. A single AGENTS.md per user (deepagents'
# MemoryMiddleware convention); the UI Memory panel edits the same row.
_MEM_FILES = {"AGENTS.md": "agents_md"}


def _read_result(content: str, offset: int, limit: int) -> ReadResult:
    fd = create_file_data(content or "")
    sliced = slice_read_response(fd, offset, limit)
    if isinstance(sliced, ReadResult):
        return sliced
    return ReadResult(file_data=FileData(content=sliced, encoding=fd.get("encoding", "utf-8")))


class MemoryBackend(BackendProtocol):
    """``/memory/AGENTS.md`` ↔ ``user_configs.agents_md``. Read+write so the agent's
    MemoryMiddleware + edit_file and the UI Memory panel share one source of truth."""

    def __init__(self, user_id: str) -> None:
        self.user_id = str(user_id or DEFAULT_USER_ID)

    def _col(self, path: str) -> str | None:
        return _MEM_FILES.get((path or "").strip("/").split("/")[-1])

    def _invalidate(self) -> None:
        # memory edits feed the system prompt — drop cached agents on change.
        try:
            from .agent_common import invalidate_user_cache

            invalidate_user_cache(self.user_id)
        except Exception:  # noqa: BLE001
            logger.debug("memory invalidate failed", exc_info=True)

    async def als(self, path: str = "/") -> LsResult:
        async with db_session() as s:
            cfg = await s.get(UserConfig, self.user_id)
            entries = []
            for fn, col in _MEM_FILES.items():
                content = (getattr(cfg, col, "") or "") if cfg else ""
                entries.append(FileInfo(path=f"/{fn}", is_dir=False, size=len(content), modified_at=""))
            return LsResult(entries=entries)

    async def aread(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        col = self._col(file_path)
        if not col:
            return ReadResult(error=f"File '{file_path}' not found")
        async with db_session() as s:
            cfg = await s.get(UserConfig, self.user_id)
            content = (getattr(cfg, col, "") or "") if cfg else ""
        return _read_result(content, offset, limit)

    async def _set(self, col: str, content: str) -> None:
        async with db_session() as s:
            cfg = await get_or_create_user_config(s, self.user_id)
            setattr(cfg, col, content or "")
        self._invalidate()

    async def awrite(self, file_path: str, content: str) -> WriteResult:
        col = self._col(file_path)
        if not col:
            return WriteResult(error=f"Cannot write {file_path}: only AGENTS.md exists in /memory/")
        await self._set(col, content)  # memory slots overwrite (no create-only error)
        return WriteResult(path=file_path)

    async def aedit(self, file_path: str, old_string: str, new_string: str, replace_all: bool = False) -> EditResult:
        col = self._col(file_path)
        if not col:
            return EditResult(error=f"Error: File '{file_path}' not found")
        async with db_session() as s:
            cfg = await s.get(UserConfig, self.user_id)
            content = (getattr(cfg, col, "") or "") if cfg else ""
        result = perform_string_replacement(content, old_string, new_string, replace_all)
        if isinstance(result, str):
            return EditResult(error=result)
        new_content, occ = result
        await self._set(col, new_content)
        return EditResult(path=file_path, occurrences=int(occ))

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        out: list[FileDownloadResponse] = []
        async with db_session() as s:
            cfg = await s.get(UserConfig, self.user_id)
            for p in paths:
                col = self._col(p)
                if not col:
                    out.append(FileDownloadResponse(path=p, content=None, error="file_not_found"))
                    continue
                content = (getattr(cfg, col, "") or "") if cfg else ""
                out.append(FileDownloadResponse(path=p, content=content.encode("utf-8"), error=None))
        return out

    async def aupload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        return [FileUploadResponse(path=p, error="permission_denied") for p, _ in files]

    # sync fallbacks (never used on the async agent path)
    def grep(self, pattern, path=None, glob=None) -> GrepResult:  # noqa: ANN001
        return GrepResult(matches=[])

    def glob(self, pattern, path=None) -> GlobResult:  # noqa: ANN001
        return GlobResult(matches=[])


def _file_bytes(sf: SkillFile) -> bytes:
    if sf.encoding == "base64":
        try:
            return base64.b64decode(sf.content or "")
        except Exception:  # noqa: BLE001
            return b""
    return (sf.content or "").encode("utf-8")


def _file_text(sf: SkillFile) -> str:
    if sf.encoding == "base64":
        return _file_bytes(sf).decode("utf-8", "replace")
    return sf.content or ""


class DbSkillsBackend(BackendProtocol):
    """Serves a skills mount from the DB — both ``/skills/global/`` (shipped, read-only;
    ``user_id=None`` → ``global_skills``) and ``/skills/user/`` (per-user, authored via
    the Skills tab; ``user_id=<uid>`` → ``user_skills``). Helper files come from
    ``skill_files`` (base64-decoded for binaries). Read-only to the agent; only ENABLED
    skills are exposed for loading. The middleware calls the async methods."""

    def __init__(self, user_id: str | None = None) -> None:
        # None => global scope; otherwise the per-user scope.
        self.user_id = str(user_id) if user_id is not None else None

    @property
    def _is_global(self) -> bool:
        return self.user_id is None

    @staticmethod
    def _parts(path: str) -> list[str]:
        return [p for p in (path or "").strip("/").split("/") if p]

    async def _list_skills(self, s):
        if self._is_global:
            return (
                await s.scalars(
                    select(GlobalSkill).where(GlobalSkill.is_active.is_(True)).order_by(GlobalSkill.name)
                )
            ).all()
        return (
            await s.scalars(
                select(UserSkill)
                .where(UserSkill.user_id == self.user_id, UserSkill.is_active.is_(True))
                .order_by(UserSkill.name)
            )
        ).all()

    async def _skill(self, s, name: str):
        if self._is_global:
            return await s.scalar(
                select(GlobalSkill).where(GlobalSkill.name == name, GlobalSkill.is_active.is_(True))
            )
        return await s.scalar(select(UserSkill).where(UserSkill.user_id == self.user_id, UserSkill.name == name))

    async def _skill_files(self, s, skill_id: str):
        col = SkillFile.global_skill_id if self._is_global else SkillFile.user_skill_id
        return (await s.scalars(select(SkillFile).where(col == skill_id))).all()

    async def _file_row(self, s, skill_id: str, filename: str):
        col = SkillFile.global_skill_id if self._is_global else SkillFile.user_skill_id
        return await s.scalar(select(SkillFile).where(col == skill_id, SkillFile.filename == filename))

    async def als(self, path: str = "/") -> LsResult:
        parts = self._parts(path)
        async with db_session() as s:
            if not parts:
                rows = await self._list_skills(s)
                return LsResult(entries=[FileInfo(path=f"/{r.name}", is_dir=True, size=0, modified_at="") for r in rows])
            name = parts[0]
            sk = await self._skill(s, name)
            if not sk:
                return LsResult(error=f"'{path}' not found")
            entries = [FileInfo(path=f"/{name}/SKILL.md", is_dir=False, size=len(sk.content or ""), modified_at="")]
            for f in await self._skill_files(s, sk.id):
                entries.append(FileInfo(path=f"/{name}/{f.filename}", is_dir=False, size=len(f.content or ""), modified_at=""))
            return LsResult(entries=entries)

    async def _resolve_bytes(self, name: str, filename: str) -> bytes | None:
        async with db_session() as s:
            sk = await self._skill(s, name)
            if not sk:
                return None
            if filename == "SKILL.md":
                return (sk.content or "").encode("utf-8")
            f = await self._file_row(s, sk.id, filename)
            return _file_bytes(f) if f else None

    async def aread(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        parts = self._parts(file_path)
        if len(parts) < 2:
            return ReadResult(error=f"File '{file_path}' not found")
        data = await self._resolve_bytes(parts[0], "/".join(parts[1:]))
        if data is None:
            return ReadResult(error=f"File '{file_path}' not found")
        return _read_result(data.decode("utf-8", "replace"), offset, limit)

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        out: list[FileDownloadResponse] = []
        for p in paths:
            parts = self._parts(p)
            data = await self._resolve_bytes(parts[0], "/".join(parts[1:])) if len(parts) >= 2 else None
            if data is None:
                out.append(FileDownloadResponse(path=p, content=None, error="file_not_found"))
            else:
                out.append(FileDownloadResponse(path=p, content=data, error=None))
        return out

    # read-only to the agent — global skills are shipped; user skills are authored via the Skills tab.
    async def awrite(self, file_path: str, content: str) -> WriteResult:
        return WriteResult(error="skills are read-only here (manage user skills via the Skills tab)")

    async def aedit(self, file_path: str, old_string: str, new_string: str, replace_all: bool = False) -> EditResult:
        return EditResult(error="skills are read-only here (manage user skills via the Skills tab)")

    async def aupload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        return [FileUploadResponse(path=p, error="permission_denied") for p, _ in files]

    def grep(self, pattern, path=None, glob=None) -> GrepResult:  # noqa: ANN001
        return GrepResult(matches=[])

    def glob(self, pattern, path=None) -> GlobResult:  # noqa: ANN001
        return GlobResult(matches=[])


class MemoriesBackend(BackendProtocol):
    """The agent's ``/memories/`` mount — a ``StoreBackend`` on namespace
    ``(uid,"memories")`` (LangGraph store) that HIDES disabled files (value
    ``enabled == False``) from the agent, mirroring how a disabled skill is
    hidden. Disabled files are filtered out of ``als`` and blocked from
    ``aread``/``adownload`` so the agent neither lists nor reads them; the UI
    still manages them via the ``/v1/memories`` endpoints. Everything else
    delegates to the wrapped ``StoreBackend``."""

    def __init__(self, user_id: str) -> None:
        self.user_id = str(user_id or DEFAULT_USER_ID)
        self._ns = (self.user_id, MEMORIES_NS)
        self._inner = StoreBackend(namespace=lambda _rt, _ns=(self.user_id, MEMORIES_NS): _ns)

    @staticmethod
    def _norm(p: str) -> str:
        return p if (p or "").startswith("/") else f"/{p or ''}"

    async def _is_enabled(self, store, path: str) -> bool:
        it = await store.aget(self._ns, self._norm(path))
        # absent (just-created by the agent, no flag) or enabled → visible.
        return it is None or (it.value or {}).get("enabled", True) is not False

    async def als(self, path: str = "/") -> LsResult:
        res = await self._inner.als(path)
        if getattr(res, "error", None) or not res.entries:
            return res
        store = get_store()
        # entries are FileInfo TypedDicts (plain dicts), not attribute objects.
        kept = [
            e
            for e in res.entries
            if e.get("is_dir") or await self._is_enabled(store, e.get("path", ""))
        ]
        return LsResult(entries=kept)

    async def aread(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        if not await self._is_enabled(get_store(), file_path):
            return ReadResult(error=f"File '{file_path}' not found")
        return await self._inner.aread(file_path, offset, limit)

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        store = get_store()
        out: list[FileDownloadResponse] = []
        for p in paths:
            if not await self._is_enabled(store, p):
                out.append(FileDownloadResponse(path=p, content=None, error="file_not_found"))
            else:
                out.append((await self._inner.adownload_files([p]))[0])
        return out

    async def awrite(self, file_path: str, content: str) -> WriteResult:
        return await self._inner.awrite(file_path, content)

    async def aedit(self, file_path: str, old_string: str, new_string: str, replace_all: bool = False) -> EditResult:
        return await self._inner.aedit(file_path, old_string, new_string, replace_all)

    async def aupload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        return await self._inner.aupload_files(files)

    def grep(self, pattern, path=None, glob=None) -> GrepResult:  # noqa: ANN001
        return GrepResult(matches=[])

    def glob(self, pattern, path=None) -> GlobResult:  # noqa: ANN001
        return GlobResult(matches=[])
