"""Per-user UI settings, backed by the ``user_configs`` table.

Surfaces the preference columns the frontend reads/writes via ``/v1/settings/ui``
as a flat dict: display name, sidebar tab order, skin (by name), theme/UX toggles,
default model + reasoning, and locale. ``skin`` is exposed by name (e.g. "default",
"ares") and resolved to its ``skin_id`` FK on write.
"""

from __future__ import annotations

import logging

from sqlalchemy import select

from .db import db_session, get_or_create_user_config
from .db.models import Skin, User, UserConfig

logger = logging.getLogger("joyjoy.usersettings")

# Columns the UI may PUT (skin handled separately; email is read-only here).
_WRITABLE = {
    "display_name": str,
    "theme": str,
    "auto_follow": bool,
    "activity_display": str,
    "default_model": str,
    "default_reasoning": str,
    "locale": str,
    "sidebar_order": list,
}


async def list_skins() -> list[dict]:
    """The shipped skin catalog (DB ``skins`` table) for the Appearance picker."""
    try:
        async with db_session() as s:
            rows = (
                await s.scalars(
                    select(Skin).where(Skin.is_active.is_(True)).order_by(Skin.sort_order)
                )
            ).all()
            return [
                {"id": r.name, "label": r.label or r.name, "color": (r.config or {}).get("color", "")}
                for r in rows
            ]
    except Exception:
        logger.debug("list_skins failed", exc_info=True)
        return []


async def read_ui(user_id: str) -> dict:
    try:
        async with db_session() as s:
            cfg = await s.get(UserConfig, str(user_id or ""))
            skin_name = "default"
            if cfg and cfg.skin_id:
                skin = await s.get(Skin, cfg.skin_id)
                if skin:
                    skin_name = skin.name
            email = await s.scalar(select(User.email).where(User.id == str(user_id or "")))
            if not cfg:
                return {"skin": skin_name, "email": email or ""}
            return {
                "display_name": cfg.display_name or "",
                "sidebar_order": cfg.sidebar_order or [],
                "skin": skin_name,
                "theme": cfg.theme or "system",
                "auto_follow": cfg.auto_follow,
                "activity_display": cfg.activity_display,
                "default_model": cfg.default_model or "",
                "default_reasoning": cfg.default_reasoning or "off",
                "locale": cfg.locale or "en",
                "email": email or "",
            }
    except Exception:
        logger.debug("read_ui failed", exc_info=True)
        return {}


async def write_ui(user_id: str, data: dict) -> dict:
    data = data if isinstance(data, dict) else {}
    try:
        async with db_session() as s:
            cfg = await get_or_create_user_config(s, user_id)
            for key, typ in _WRITABLE.items():
                if key not in data:
                    continue
                val = data[key]
                if key == "display_name":
                    cfg.display_name = str(val or "")[:128]
                elif typ is bool:
                    setattr(cfg, key, bool(val))
                elif typ is list:
                    setattr(cfg, key, list(val) if isinstance(val, list) else [])
                else:
                    setattr(cfg, key, str(val or ""))
            if "skin" in data:
                skin = await s.scalar(select(Skin).where(Skin.name == str(data["skin"] or "")))
                if skin:
                    cfg.skin_id = skin.id
    except Exception as e:
        logger.warning("write_ui failed", exc_info=True)
        return {"ok": False, "error": str(e)}
    return {"ok": True}
