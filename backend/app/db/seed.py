"""Idempotent seeds for the global (shipped) catalogs: providers, skins, the
base model catalog, the global MCP servers, and the global skills. Runs on every
startup after ``init_db``; each row is inserted only when its unique key is absent,
so it is safe to re-run and never clobbers admin edits.

Sources mirror the pre-DB world so behaviour is unchanged:
  providers ← agent.PROVIDER_TYPES   models ← settings.model_specs
  skins     ← frontend SKINS         mcp    ← settings.mcp_global_config (json)
  skills    ← settings.global_skills_dir/*/SKILL.md
"""

from __future__ import annotations

import json
import logging
import os

from sqlalchemy import select

from .crypto import encrypt_secrets
from .engine import db_session
from .models import GlobalMcp, GlobalModel, GlobalProvider, GlobalSkill, Skin

logger = logging.getLogger("joyjoy.seed")

# Frontend src/store/settings.ts SKINS (kept in sync by hand — tiny + stable).
_SKINS = [
    {"name": "default", "label": "Gold", "color": "#FFD700"},
    {"name": "ares", "label": "Ares", "color": "#FF4444"},
    {"name": "poseidon", "label": "Poseidon", "color": "#0EA5E9"},
    {"name": "sisyphus", "label": "Sisyphus", "color": "#A78BFA"},
    {"name": "mono", "label": "Mono", "color": "#CCCCCC"},
]


def _parse_description(md: str) -> str:
    """Pull ``description:`` out of a SKILL.md YAML frontmatter block."""
    lines = md.splitlines()
    if not lines or lines[0].strip() != "---":
        return ""
    for ln in lines[1:]:
        if ln.strip() == "---":
            break
        if ln.lstrip().lower().startswith("description:"):
            return ln.split(":", 1)[1].strip().strip("\"'")
    return ""


def _lines_from(value) -> str:
    """Normalize an MCP arg list / env|header dict into the textarea form the
    UI + agent loader expect (one item / KEY=value per line)."""
    if isinstance(value, list):
        return "\n".join(str(v) for v in value)
    if isinstance(value, dict):
        return "\n".join(f"{k}={v}" for k, v in value.items())
    return str(value or "")


async def _seed_skins(session) -> int:
    n = 0
    for i, sk in enumerate(_SKINS):
        exists = await session.scalar(select(Skin.id).where(Skin.name == sk["name"]))
        if exists:
            continue
        session.add(Skin(name=sk["name"], label=sk["label"], config={"color": sk["color"]}, sort_order=i))
        n += 1
    return n


async def _seed_providers(session) -> int:
    from ..agent import PROVIDER_TYPES  # lazy: avoids import cycle at module load

    n = 0
    for i, p in enumerate(PROVIDER_TYPES):
        exists = await session.scalar(select(GlobalProvider.id).where(GlobalProvider.name == p["id"]))
        if exists:
            continue
        session.add(
            GlobalProvider(
                name=p["id"], label=p.get("label", p["id"]),
                config_schema={"fields": p.get("fields", [])}, sort_order=i,
            )
        )
        n += 1
    return n


async def _seed_models(session, settings) -> int:
    """Seed the base model catalog (settings.model_specs). Secret fields are
    Fernet-encrypted before they hit the DB."""
    # provider name -> id
    rows = (await session.execute(select(GlobalProvider.name, GlobalProvider.id))).all()
    pid = {name: _id for name, _id in rows}
    n = 0
    for mid, spec in settings.model_specs.items():
        exists = await session.scalar(select(GlobalModel.id).where(GlobalModel.model_id == mid))
        if exists:
            continue
        provider = str(spec.get("provider") or "azure_openai")
        session.add(
            GlobalModel(
                model_id=mid,
                provider_id=pid.get(provider) or pid.get("azure_openai"),
                settings=encrypt_secrets(spec),
                is_active=True,
            )
        )
        n += 1
    return n


async def _seed_mcps(session, settings) -> int:
    path = os.path.abspath(settings.mcp_global_config)
    if not os.path.isfile(path):
        logger.info("No global MCP config at %s — skipping MCP seed", path)
        return 0
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        logger.warning("Could not read global MCP config %s", path, exc_info=True)
        return 0
    servers = cfg.get("mcpServers", cfg) if isinstance(cfg, dict) else {}
    n = 0
    for name, s in servers.items():
        if not isinstance(s, dict):
            continue
        exists = await session.scalar(select(GlobalMcp.id).where(GlobalMcp.name == name))
        if exists:
            continue
        url = s.get("url", "")
        transport = s.get("transport") or ("http" if url else "stdio")
        session.add(
            GlobalMcp(
                name=name, transport=transport,
                command=s.get("command", ""), args=_lines_from(s.get("args")),
                env=_lines_from(s.get("env")), url=url, headers=_lines_from(s.get("headers")),
                is_active=True,
            )
        )
        n += 1
    return n


async def _seed_skills(session, settings) -> int:
    root = os.path.abspath(settings.global_skills_dir)
    if not os.path.isdir(root):
        logger.info("No global skills dir at %s — skipping skill seed", root)
        return 0
    n = 0
    for name in sorted(os.listdir(root)):
        d = os.path.join(root, name)
        skill_md = os.path.join(d, "SKILL.md")
        if not os.path.isdir(d) or not os.path.isfile(skill_md):
            continue
        exists = await session.scalar(select(GlobalSkill.id).where(GlobalSkill.name == name))
        if exists:
            continue
        try:
            with open(skill_md, encoding="utf-8") as f:
                content = f.read()
        except Exception:
            logger.warning("Could not read skill %s", skill_md, exc_info=True)
            continue
        session.add(
            GlobalSkill(name=name, description=_parse_description(content), content=content, is_active=True)
        )
        n += 1
    return n


async def seed_all(settings) -> None:
    """Run every seed in dependency order (providers before models)."""
    async with db_session() as session:
        skins = await _seed_skins(session)
        providers = await _seed_providers(session)
    # models depend on providers existing/committed
    async with db_session() as session:
        models = await _seed_models(session, settings)
        mcps = await _seed_mcps(session, settings)
        skills = await _seed_skills(session, settings)
    if any((skins, providers, models, mcps, skills)):
        logger.info(
            "Seeded: %d skins, %d providers, %d models, %d mcp, %d skills",
            skins, providers, models, mcps, skills,
        )
