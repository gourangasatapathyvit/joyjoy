"""DB-backed deepagents backends — the bridge that lets the agent read/write its
``/memory/`` and ``/skills/user/`` mounts straight against the relational DB
(``user_configs`` / ``user_skills`` / ``skill_files``) instead of the KV store.

These mount under ``CompositeBackend`` (see ``agent.build_backend``), which strips
the route prefix and calls the **async** methods (``als``/``aread``/``awrite``/
``aedit``/``adownload_files``) — so we override those directly with async DB I/O.
The sync methods are graceful no-ops/errors; the agent runs async and never hits
them. ``grep``/``glob`` return empty (these mounts aren't text-searched).
"""

from __future__ import annotations

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
from deepagents.backends.utils import (
    create_file_data,
    perform_string_replacement,
    slice_read_response,
)
from sqlalchemy import select

from .db import db_session
from .db.models import SkillFile, UserConfig, UserSkill

logger = logging.getLogger("joyjoy.dbfs")

# /memory/<file> -> UserConfig column (the frontend memory sections live here too).
_MEM_FILES = {"MEMORY.md": "notes", "USER.md": "about_you", "SOUL.md": "persona"}


def _read_result(content: str, offset: int, limit: int) -> ReadResult:
    fd = create_file_data(content or "")
    sliced = slice_read_response(fd, offset, limit)
    if isinstance(sliced, ReadResult):
        return sliced
    return ReadResult(file_data=FileData(content=sliced, encoding=fd.get("encoding", "utf-8")))


class MemoryBackend(BackendProtocol):
    """``/memory/`` ↔ ``user_configs`` (notes / about_you / persona). Read+write so
    the agent's memory tools and the UI Memory panel share one source of truth."""

    def __init__(self, user_id: str) -> None:
        self.user_id = str(user_id or "default")

    def _col(self, path: str) -> str | None:
        return _MEM_FILES.get((path or "").strip("/").split("/")[-1])

    def _invalidate(self) -> None:
        # soul/profile/notes feed the system prompt — drop cached agents on change.
        try:
            from .agent import _invalidate_user_cache

            _invalidate_user_cache(self.user_id)
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
            cfg = await s.get(UserConfig, self.user_id)
            if cfg is None:
                cfg = UserConfig(user_id=self.user_id)
                s.add(cfg)
            setattr(cfg, col, content or "")
        self._invalidate()

    async def awrite(self, file_path: str, content: str) -> WriteResult:
        col = self._col(file_path)
        if not col:
            return WriteResult(error=f"Cannot write {file_path}: only MEMORY.md / USER.md / SOUL.md exist")
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


class UserSkillsBackend(BackendProtocol):
    """``/skills/user/`` ↔ ``user_skills`` + ``skill_files`` (read-only to the agent;
    authored via the Skills tab CRUD). Only ENABLED skills are exposed for loading."""

    def __init__(self, user_id: str) -> None:
        self.user_id = str(user_id or "default")

    @staticmethod
    def _parts(path: str) -> list[str]:
        return [p for p in (path or "").strip("/").split("/") if p]

    async def als(self, path: str = "/") -> LsResult:
        parts = self._parts(path)
        async with db_session() as s:
            if not parts:
                rows = (
                    await s.scalars(
                        select(UserSkill)
                        .where(UserSkill.user_id == self.user_id, UserSkill.is_active.is_(True))
                        .order_by(UserSkill.name)
                    )
                ).all()
                return LsResult(entries=[FileInfo(path=f"/{r.name}", is_dir=True, size=0, modified_at="") for r in rows])
            name = parts[0]
            sk = await s.scalar(select(UserSkill).where(UserSkill.user_id == self.user_id, UserSkill.name == name))
            if not sk:
                return LsResult(error=f"'{path}' not found")
            entries = [FileInfo(path=f"/{name}/SKILL.md", is_dir=False, size=len(sk.content or ""), modified_at="")]
            files = (await s.scalars(select(SkillFile).where(SkillFile.user_skill_id == sk.id))).all()
            entries.extend(
                FileInfo(path=f"/{name}/{f.filename}", is_dir=False, size=len(f.content or ""), modified_at="")
                for f in files
            )
            return LsResult(entries=entries)

    async def _read_file(self, name: str, filename: str) -> str | None:
        async with db_session() as s:
            sk = await s.scalar(select(UserSkill).where(UserSkill.user_id == self.user_id, UserSkill.name == name))
            if not sk:
                return None
            if filename == "SKILL.md":
                return sk.content or ""
            f = await s.scalar(
                select(SkillFile).where(SkillFile.user_skill_id == sk.id, SkillFile.filename == filename)
            )
            return (f.content or "") if f else None

    async def aread(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        parts = self._parts(file_path)
        if len(parts) < 2:
            return ReadResult(error=f"File '{file_path}' not found")
        content = await self._read_file(parts[0], "/".join(parts[1:]))
        if content is None:
            return ReadResult(error=f"File '{file_path}' not found")
        return _read_result(content, offset, limit)

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        out: list[FileDownloadResponse] = []
        for p in paths:
            parts = self._parts(p)
            content = await self._read_file(parts[0], "/".join(parts[1:])) if len(parts) >= 2 else None
            if content is None:
                out.append(FileDownloadResponse(path=p, content=None, error="file_not_found"))
            else:
                out.append(FileDownloadResponse(path=p, content=content.encode("utf-8"), error=None))
        return out

    # read-only to the agent — authoring happens through the Skills tab CRUD.
    async def awrite(self, file_path: str, content: str) -> WriteResult:
        return WriteResult(error="user skills are managed via the Skills tab")

    async def aedit(self, file_path: str, old_string: str, new_string: str, replace_all: bool = False) -> EditResult:
        return EditResult(error="user skills are managed via the Skills tab")

    async def aupload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        return [FileUploadResponse(path=p, error="permission_denied") for p, _ in files]

    def grep(self, pattern, path=None, glob=None) -> GrepResult:  # noqa: ANN001
        return GrepResult(matches=[])

    def glob(self, pattern, path=None) -> GlobResult:  # noqa: ANN001
        return GlobResult(matches=[])
