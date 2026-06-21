"""Per-user UI settings (currently the sidebar tab order).

Honors the deployment split: in DEV (``settings.prod`` falsey) the settings are a
plain JSON file at ``data/users/<uid>/ui.json`` (easy to inspect/edit, like
models.json / mcp.json); in PROD they go to the LangGraph store — Postgres — the
same place sessions / skills / memory live.
"""

from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger("joyjoy.usersettings")

_KEY = "ui"


def _ns(user_id: str) -> tuple[str, str]:
    return (str(user_id or "default"), "settings")


def _path(settings, user_id: str) -> str:
    return os.path.join(settings.user_data_root, str(user_id or "default"), "ui.json")


def _is_prod(settings) -> bool:
    return bool(getattr(settings, "prod", False))


async def read_ui(settings, store, user_id: str) -> dict:
    if _is_prod(settings):
        try:
            item = await store.aget(_ns(user_id), _KEY)
            val = getattr(item, "value", None)
            return dict(val) if isinstance(val, dict) else {}
        except Exception:
            logger.debug("read_ui (store) failed", exc_info=True)
            return {}
    try:
        with open(_path(settings, user_id), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception:
        logger.debug("read_ui (json) failed", exc_info=True)
        return {}


async def write_ui(settings, store, user_id: str, data: dict) -> dict:
    data = data if isinstance(data, dict) else {}
    if _is_prod(settings):
        try:
            await store.aput(_ns(user_id), _KEY, data)
        except Exception:
            logger.warning("write_ui (store) failed", exc_info=True)
            return {"ok": False, "error": "store write failed"}
        return {"ok": True}
    try:
        path = _path(settings, user_id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
    except OSError as e:
        logger.warning("write_ui (json) failed", exc_info=True)
        return {"ok": False, "error": str(e)}
    return {"ok": True}
