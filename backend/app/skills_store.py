"""Skills: UI introspection (list + content) and per-user CRUD (single-file +
multi-file skills, zip import). Global skills are READ-ONLY here — writes only
ever touch the user's own ``user_skills``/``skill_files`` rows. Everything is
served from the DB (see dbfs.DbSkillsBackend for the agent-facing mount)."""

from __future__ import annotations

import base64
import io
import logging
import zipfile

from sqlalchemy import delete as sa_delete
from sqlalchemy import select

from .agent_common import invalidate_user_cache as _invalidate_user_cache
from .agent_common import valid_name as _valid_name
from .config import Settings
from .constants import MAX_SKILL_FILE_BYTES, MAX_SKILL_FILES, MAX_SKILL_TOTAL_BYTES
from .db import db_session
from .db.models import GlobalSkill, SkillFile, UserSkill
from .dbfs import _file_bytes, _file_text

logger = logging.getLogger("joyjoy.agent")


def _parse_skill_frontmatter(text: str, fallback_name: str) -> dict:
    """Extract name+description from SKILL.md YAML frontmatter text (best-effort)."""
    name, desc = fallback_name, ""
    try:
        if text.lstrip().startswith("---"):
            block = text.split("---", 2)
            if len(block) >= 3:
                for line in block[1].splitlines():
                    k, sep, v = line.partition(":")
                    if not sep:
                        continue
                    k, v = k.strip().lower(), v.strip().strip("'\"")
                    if k == "name" and v:
                        name = v
                    elif k == "description" and v:
                        desc = v
    except Exception:  # noqa: BLE001
        logger.debug("failed to parse skill frontmatter", exc_info=True)
    return {"name": name, "description": desc}


async def list_skills(settings: Settings, user_id: str) -> list[dict]:
    """Global skills (read-only, ``global_skills`` table) + per-user skills
    (``user_skills`` table) for the UI Skills tab."""
    skills: list[dict] = []
    async with db_session() as s:
        grows = (
            await s.scalars(
                select(GlobalSkill).where(GlobalSkill.is_active.is_(True)).order_by(GlobalSkill.name)
            )
        ).all()
        for g in grows:
            skills.append(
                {"name": g.name, "description": g.description or "", "scope": "global",
                 "editable": False, "enabled": True, "builtin": True}
            )
        urows = (
            await s.scalars(
                select(UserSkill).where(UserSkill.user_id == str(user_id)).order_by(UserSkill.name)
            )
        ).all()
        for u in urows:
            skills.append(
                {"name": u.name, "description": u.description or "", "scope": "user",
                 "editable": True, "enabled": bool(u.is_active)}
            )
    return skills


async def read_skill_content(settings: Settings, user_id: str, name: str, file: str | None = None) -> dict:
    """Read a global skill (shipped, read-only) or a per-user skill — both entirely
    from the DB (``global_skills``/``user_skills`` + ``skill_files``) for the UI viewer.

    Returns ``{success, name, content, linked_files}`` on success, or
    ``{success: False, error}`` when not found.
    """
    if not name:
        return {"success": False, "error": "name required"}
    async with db_session() as s:
        gs = await s.scalar(select(GlobalSkill).where(GlobalSkill.name == name, GlobalSkill.is_active.is_(True)))
        if gs:
            spec = (gs, SkillFile.global_skill_id, "global", False, True)
        else:
            us = await s.scalar(select(UserSkill).where(UserSkill.user_id == str(user_id), UserSkill.name == name))
            if not us:
                return {"success": False, "error": f"Skill '{name}' not found.", "available_skills": [], "linked_files": {}}
            spec = (us, SkillFile.user_skill_id, "user", True, bool(us.is_active))
        sk, file_col, scope, editable, enabled = spec
        if file:
            f = await s.scalar(select(SkillFile).where(file_col == sk.id, SkillFile.filename == file))
            if not f:
                return {"success": False, "error": "File not found"}
            return {"success": True, "name": name, "content": _file_text(f), "path": file}
        files = (await s.scalars(select(SkillFile).where(file_col == sk.id))).all()
        return {
            "success": True, "name": name, "scope": scope, "editable": editable,
            "enabled": enabled, "content": sk.content or "",
            "linked_files": {f.filename: True for f in files},
        }


async def read_skill_tree(settings: Settings, user_id: str, name: str) -> list[tuple[str, bytes]] | None:
    """All files of a skill as ``(relpath, bytes)`` — SKILL.md + helper files,
    binary-safe (base64 helper files decoded). Used to materialize a skill into a
    sandbox so its scripts can run. Global skills resolve first, then per-user."""
    async with db_session() as s:
        gs = await s.scalar(select(GlobalSkill).where(GlobalSkill.name == name, GlobalSkill.is_active.is_(True)))
        if gs:
            sk, file_col = gs, SkillFile.global_skill_id
        else:
            us = await s.scalar(select(UserSkill).where(UserSkill.user_id == str(user_id), UserSkill.name == name))
            if not us:
                return None
            sk, file_col = us, SkillFile.user_skill_id
        out: list[tuple[str, bytes]] = [("SKILL.md", (sk.content or "").encode("utf-8"))]
        files = (await s.scalars(select(SkillFile).where(file_col == sk.id))).all()
        for f in files:
            out.append((f.filename, _file_bytes(f)))
    return out


# ---- per-user skill CRUD. Global is READ-ONLY — writes only touch user rows. ----
async def save_user_skill(user_id, name, content) -> dict:
    """Create or overwrite a per-user skill (enables it). The description is parsed
    from the SKILL.md frontmatter so the Skills list shows it."""
    name = (name or "").strip()
    if not _valid_name(name):
        return {"ok": False, "error": "invalid skill name"}
    desc = _parse_skill_frontmatter(content or "", name).get("description", "")
    async with db_session() as s:
        sk = await s.scalar(select(UserSkill).where(UserSkill.user_id == str(user_id), UserSkill.name == name))
        if sk is None:
            sk = UserSkill(user_id=str(user_id), name=name)
            s.add(sk)
        sk.content = content or ""
        sk.description = desc
        sk.is_active = True
    _invalidate_user_cache(user_id)
    return {"ok": True, "name": name, "path": f"/skills/user/{name}/SKILL.md"}


async def delete_user_skill(user_id, name) -> dict:
    name = (name or "").strip()
    if not _valid_name(name):
        return {"ok": False, "error": "invalid skill name"}
    async with db_session() as s:
        res = await s.execute(
            sa_delete(UserSkill).where(UserSkill.user_id == str(user_id), UserSkill.name == name)
        )
        deleted = res.rowcount or 0  # skill_files cascade via FK ondelete=CASCADE
    if deleted:
        _invalidate_user_cache(user_id)
    return {"ok": deleted > 0, "name": name, "deleted": deleted}

async def toggle_user_skill(user_id, name, enabled) -> dict:
    """Enable/disable a user skill (is_active flag; disabled skills aren't loaded)."""
    name = (name or "").strip()
    if not _valid_name(name):
        return {"ok": False, "error": "invalid skill name"}
    async with db_session() as s:
        sk = await s.scalar(select(UserSkill).where(UserSkill.user_id == str(user_id), UserSkill.name == name))
        if sk is None:
            return {"ok": False, "error": f"skill '{name}' not found"}
        sk.is_active = bool(enabled)
    _invalidate_user_cache(user_id)
    return {"ok": True, "name": name, "enabled": bool(enabled)}


# ---- per-user skill FILES (multi-file skills: SKILL.md + helper tree) ----
# Size caps live in constants.py (MAX_SKILL_FILES / MAX_SKILL_FILE_BYTES /
# MAX_SKILL_TOTAL_BYTES), imported above.


def _safe_rel(path: str) -> str | None:
    """Normalize a skill-relative file path; reject traversal/absolute paths."""
    p = (path or "").replace("\\", "/").strip().lstrip("/")
    parts = [seg for seg in p.split("/") if seg]
    if not parts or any(seg in (".", "..") for seg in parts):
        return None
    return "/".join(parts)


async def _get_or_create_user_skill(s, user_id, name):
    sk = await s.scalar(select(UserSkill).where(UserSkill.user_id == str(user_id), UserSkill.name == name))
    if sk is None:
        sk = UserSkill(user_id=str(user_id), name=name, content="", description="")
        s.add(sk)
        await s.flush()
    return sk


async def save_user_skill_file(user_id, name, path, content, encoding="utf-8") -> dict:
    """Create/overwrite one file in a user skill. ``path='SKILL.md'`` updates the
    skill body; any other path is a helper file (``skill_files``). ``encoding`` is
    'utf-8' (text) or 'base64' (binary). Creates the skill if it doesn't exist."""
    name = (name or "").strip()
    if not _valid_name(name):
        return {"ok": False, "error": "invalid skill name"}
    rel = _safe_rel(path)
    if not rel:
        return {"ok": False, "error": "invalid file path"}
    raw_len = len(content or "")
    if encoding == "base64":
        try:
            raw_len = len(base64.b64decode(content or ""))
        except Exception:
            return {"ok": False, "error": "invalid base64 content"}
    if raw_len > MAX_SKILL_FILE_BYTES:
        return {"ok": False, "error": "file too large"}
    async with db_session() as s:
        sk = await _get_or_create_user_skill(s, user_id, name)
        if rel == "SKILL.md":
            sk.content = content or ""
            sk.description = _parse_skill_frontmatter(content or "", name).get("description", "")
            sk.is_active = True
        else:
            f = await s.scalar(
                select(SkillFile).where(SkillFile.user_skill_id == sk.id, SkillFile.filename == rel)
            )
            if f is None:
                f = SkillFile(user_skill_id=sk.id, filename=rel)
                s.add(f)
            f.content = content or ""
            f.encoding = "base64" if encoding == "base64" else "utf-8"
    _invalidate_user_cache(user_id)
    return {"ok": True, "name": name, "path": rel}


async def delete_user_skill_file(user_id, name, path) -> dict:
    name = (name or "").strip()
    rel = _safe_rel(path)
    if not _valid_name(name) or not rel:
        return {"ok": False, "error": "invalid skill/path"}
    if rel == "SKILL.md":
        return {"ok": False, "error": "cannot delete SKILL.md — delete the whole skill instead"}
    async with db_session() as s:
        sk = await s.scalar(select(UserSkill).where(UserSkill.user_id == str(user_id), UserSkill.name == name))
        if not sk:
            return {"ok": False, "error": "skill not found"}
        res = await s.execute(
            sa_delete(SkillFile).where(SkillFile.user_skill_id == sk.id, SkillFile.filename == rel)
        )
        existed = (res.rowcount or 0) > 0
    if existed:
        _invalidate_user_cache(user_id)
    return {"ok": existed, "name": name, "path": rel}


async def import_user_skill(user_id, name, zip_b64) -> dict:
    """Create/replace a user skill from a base64-encoded zip of a skill folder
    (SKILL.md + helper tree). Binary files are stored base64. Replaces the skill's
    existing files. Caps file count / per-file / total size."""
    name = (name or "").strip()
    if not _valid_name(name):
        return {"ok": False, "error": "invalid skill name"}
    # Guard the encoded payload BEFORE decoding/buffering — a base64 string is ~4/3
    # its decoded size, so cap it against the total-skill budget to reject oversized
    # uploads up front rather than buffering an unbounded blob into memory.
    if len(zip_b64 or "") > MAX_SKILL_TOTAL_BYTES * 4 // 3 + 1024:
        return {"ok": False, "error": "zip too large"}
    try:
        zf = zipfile.ZipFile(io.BytesIO(base64.b64decode(zip_b64 or "")))
    except Exception:
        return {"ok": False, "error": "invalid zip"}
    infos = [zi for zi in zf.infolist() if not zi.is_dir()]
    md = [zi for zi in infos if zi.filename.replace("\\", "/").rsplit("/", 1)[-1] == "SKILL.md"]
    if not md:
        return {"ok": False, "error": "zip must contain a SKILL.md"}
    md_path = min((zi.filename.replace("\\", "/") for zi in md), key=lambda n: n.count("/"))
    root = md_path[: md_path.rfind("SKILL.md")]  # prefix incl. trailing slash (or "")
    collected: list[tuple[str, bytes]] = []
    total = 0
    for zi in infos:
        nn = zi.filename.replace("\\", "/")
        if root and not nn.startswith(root):
            continue
        rel = _safe_rel(nn[len(root):])
        if not rel:
            continue
        if zi.file_size > MAX_SKILL_FILE_BYTES:
            return {"ok": False, "error": f"{rel} too large"}
        total += zi.file_size
        if total > MAX_SKILL_TOTAL_BYTES:
            return {"ok": False, "error": "skill too large"}
        if len(collected) >= MAX_SKILL_FILES:
            return {"ok": False, "error": "too many files"}
        collected.append((rel, zf.read(zi)))
    async with db_session() as s:
        sk = await _get_or_create_user_skill(s, user_id, name)
        await s.execute(sa_delete(SkillFile).where(SkillFile.user_skill_id == sk.id))
        nfiles = 0
        for rel, data in collected:
            if rel == "SKILL.md":
                text = data.decode("utf-8", "replace")
                sk.content = text
                sk.description = _parse_skill_frontmatter(text, name).get("description", "")
                sk.is_active = True
                continue
            try:
                content, enc = data.decode("utf-8"), "utf-8"
            except UnicodeDecodeError:
                content, enc = base64.b64encode(data).decode("ascii"), "base64"
            s.add(SkillFile(user_skill_id=sk.id, filename=rel, content=content, encoding=enc))
            nfiles += 1
    _invalidate_user_cache(user_id)
    return {"ok": True, "name": name, "files": nfiles}
