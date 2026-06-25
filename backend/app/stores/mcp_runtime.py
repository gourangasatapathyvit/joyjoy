"""MCP plugins (global + per-user): connection building, tool loading, UI
introspection, and per-user CRUD. Secrets in command/args/url/headers/env stay
as ``${VAR}`` references — the real value lives in ``.env`` (os.environ) and is
expanded only when the connection is built."""

from __future__ import annotations

import asyncio
import logging
import os

from langchain_mcp_adapters.client import MultiServerMCPClient
from sqlalchemy import delete as sa_delete
from sqlalchemy import select

from app.agent.agent_common import invalidate_user_cache as _invalidate_user_cache
from app.agent.agent_common import valid_name as _valid_name
from app.core.config import Settings
from app.core.constants import DEFAULT_USER_ID, MCP_PROBE_TIMEOUT_S
from app.db import db_session
from app.db.models import GlobalMcp, UserMcp
from app.core.enums import McpStatus
from app.core.textutils import parse_kv, split_lines

logger = logging.getLogger("joyjoy.agent")


def _expand_env_vars(value):
    """Expand ``${VAR}``/``$VAR`` (from os.environ) in strings / lists / dicts."""
    if isinstance(value, str):
        return os.path.expandvars(value)
    if isinstance(value, list):
        return [_expand_env_vars(v) for v in value]
    if isinstance(value, dict):
        return {k: _expand_env_vars(v) for k, v in value.items()}
    return value


def _to_connections(servers: dict, extra_env: dict | None = None) -> dict:
    """Convert .mcp.json ``mcpServers`` entries to langchain-mcp-adapters connections.

    ``${VAR}`` references in command/args/url/headers/env expand from the process
    env (the backend loads ``.env`` into os.environ at startup), so API keys stay
    out of the config file and only the referenced var reaches the server.

    ``extra_env`` (per-caller values, e.g. the resolved ``WORKSPACE_ROOT`` +
    ``JOYJOY_USER_ID`` for the workspace-fs server) is merged into every stdio
    server's env — harmless to servers that ignore it.
    """
    conns: dict[str, dict] = {}
    for name, cfg in (servers or {}).items():
        if not isinstance(cfg, dict):
            continue
        if cfg.get("url"):
            conns[name] = {"transport": cfg.get("transport") or "streamable_http", "url": _expand_env_vars(cfg["url"])}
            if cfg.get("headers"):
                conns[name]["headers"] = _expand_env_vars(cfg["headers"])
        elif cfg.get("command"):
            conns[name] = {
                "transport": "stdio",
                "command": _expand_env_vars(cfg["command"]),
                "args": _expand_env_vars(list(cfg.get("args") or [])),
            }
            # MCP stdio passes ONLY this env to the child (no inherited PATH), so always
            # provide the parent's PATH/HOME/cache vars so uvx/python/npx servers can be
            # found + run; then overlay the config's env (e.g. an API key reference).
            env = {
                k: os.environ[k]
                for k in ("PATH", "HOME", "USER", "LANG", "LC_ALL", "TMPDIR", "NODE_PATH",
                          "npm_config_cache", "XDG_CACHE_HOME", "XDG_DATA_HOME", "UV_CACHE_DIR")
                if k in os.environ
            }
            if extra_env:
                env.update({k: str(v) for k, v in extra_env.items()})
            env.update(_expand_env_vars(cfg.get("env") or {}))
            conns[name]["env"] = env
    return conns


def _mcp_row_to_cfg(row) -> dict:
    """An MCP table row -> the ``.mcp.json``-shaped cfg dict the connection builder
    and the UI describe path expect (args as a list; env/headers as dicts)."""
    cfg: dict = {"enabled": bool(row.is_active)}
    if row.url:
        cfg["url"] = row.url
        cfg["transport"] = row.transport or "streamable_http"
        if row.headers:
            cfg["headers"] = parse_kv(row.headers)
    elif row.command:
        cfg["command"] = row.command
        cfg["args"] = split_lines(row.args)
        if row.env:
            cfg["env"] = parse_kv(row.env)
    return cfg


async def _merged_mcp_servers(user_id: str) -> dict:
    """{name: (cfg, scope)} — global servers first, per-user entries override/extend."""
    merged: dict[str, tuple[dict, str]] = {}
    async with db_session() as s:
        for g in (await s.scalars(select(GlobalMcp).order_by(GlobalMcp.name))).all():
            merged[g.name] = (_mcp_row_to_cfg(g), "global")
        if user_id:
            urows = (await s.scalars(select(UserMcp).where(UserMcp.user_id == str(user_id)))).all()
            for u in urows:
                merged[u.name] = (_mcp_row_to_cfg(u), "user")
    return merged


async def load_mcp_tools(settings: Settings, user_id: str) -> list:
    """Load global + per-user MCP tools (user entries override/extend global; disabled
    skipped). Each server is loaded independently so one unreachable provider (e.g. a
    copied-but-not-running server) can't blank out everyone's tools."""
    # Per-caller env for the workspace-fs server (and harmless to others): the
    # ABSOLUTE workspace root + this user's id, so the stdio child resolves the
    # same per-user dir as the main process regardless of its own cwd.
    extra_env = {
        "WORKSPACE_ROOT": os.path.abspath(settings.workspace_root_dir),
        "JOYJOY_USER_ID": str(user_id or DEFAULT_USER_ID),
    }
    conns = _to_connections(
        {
            n: cfg for n, (cfg, _s) in (await _merged_mcp_servers(user_id)).items()
            if not (isinstance(cfg, dict) and cfg.get("enabled") is False)
            # workspace-fs targets the HOST dir; when the sandbox owns the workspace
            # the agent's shell does rm/mv/mkdir, so retire it to avoid touching the
            # wrong (unused) host dir.
            and not (settings.sandbox_enabled and n == "workspace-fs")
        },
        extra_env=extra_env,
    )
    if not conns:
        return []

    tools: list = []
    for name, conn in conns.items():
        try:
            tools.extend(
                await asyncio.wait_for(
                    MultiServerMCPClient({name: conn}).get_tools(), timeout=MCP_PROBE_TIMEOUT_S
                )
            )
        except Exception:  # noqa: BLE001 - one bad/slow server shouldn't drop the rest (incl. timeout)
            logger.warning("MCP server '%s' failed/timed-out for user=%s (skipped)", name, user_id, exc_info=True)
    logger.info("loaded %d MCP tool(s) for user=%s from servers=%s", len(tools), user_id, list(conns))
    return tools


def _tool_schema_summary(tool) -> list[dict]:
    """Compact parameter list for a tool, matching the webui's MCP-tools shape."""
    out: list[dict] = []
    try:
        args = getattr(tool, "args", None) or {}
        required: list = []
        sch = getattr(tool, "args_schema", None)
        if isinstance(sch, dict):
            required = sch.get("required") or []
        for pname, pinfo in args.items():
            pinfo = pinfo if isinstance(pinfo, dict) else {}
            out.append({
                "name": pname,
                "type": pinfo.get("type") or "",
                "required": pname in required,
                "description": pinfo.get("description") or "",
            })
    except Exception:  # noqa: BLE001 - schema introspection is best-effort
        logger.debug("schema summary failed for tool", exc_info=True)
    return out


async def describe_mcp(settings: Settings, user_id: str) -> tuple[list[dict], list[dict]]:
    """Return ``(servers, tools)`` describing global+user MCP for a user.

    Each server is probed individually so tools carry their originating server +
    scope (``global``/``user``) and each server reports an accurate tool count and
    live ``status`` (``active`` if it connected, else ``invalid_config``).
    """
    servers_out: list[dict] = []
    tools_out: list[dict] = []
    for name, (cfg, scope) in (await _merged_mcp_servers(user_id)).items():
        conn = _to_connections({name: cfg})  # expanded — used only to probe
        cfg_d = cfg if isinstance(cfg, dict) else {}
        transport = "http" if cfg_d.get("url") else ("stdio" if cfg_d.get("command") else "unknown")
        enabled = not (cfg_d.get("enabled") is False)
        entry = {
            "name": name,
            "scope": scope,
            "transport": transport,
            "enabled": enabled,
            "status": McpStatus.CONFIGURED,
            "tool_count": None,
            # Show only command/args/url for display. env/headers are NEVER returned
            # (they may hold ${VAR} secret refs / inline values) — the UI doesn't use them.
            "command": cfg_d.get("command"),
            "args": cfg_d.get("args") or [],
            "url": cfg_d.get("url"),
        }
        if not conn:
            entry["status"] = McpStatus.INVALID_CONFIG
            servers_out.append(entry)
            continue
        # Mirror load_mcp_tools: in sandbox mode the agent does file CRUD via the
        # sandbox shell, so the host-targeting workspace-fs server is retired. Report
        # it as disabled here rather than probing a server the agent never gets.
        if settings.sandbox_enabled and name == "workspace-fs":
            entry["enabled"] = False
            entry["status"] = McpStatus.DISABLED
            servers_out.append(entry)
            continue
        if not enabled:
            entry["status"] = McpStatus.DISABLED
            servers_out.append(entry)
            continue
        try:
            tls = await asyncio.wait_for(MultiServerMCPClient(conn).get_tools(), timeout=MCP_PROBE_TIMEOUT_S)
            entry["tool_count"] = len(tls)
            entry["status"] = McpStatus.ACTIVE
            for tl in tls:
                tools_out.append({
                    "name": getattr(tl, "name", ""),
                    "server": name,
                    "scope": scope,
                    "status": McpStatus.ACTIVE,  # webui renders this as the tool's status badge
                    "description": getattr(tl, "description", "") or "",
                    "schema_summary": _tool_schema_summary(tl),  # webui reads `schema_summary`
                })
        except Exception:  # noqa: BLE001 - one bad server shouldn't blank the list
            logger.exception("failed to probe MCP server %s for user=%s", name, user_id)
            entry["status"] = McpStatus.INVALID_CONFIG
        servers_out.append(entry)
    return servers_out, tools_out


# ---- per-user MCP CRUD (global is read-only) ----
async def _is_global_mcp(name) -> bool:
    async with db_session() as s:
        return (await s.scalar(select(GlobalMcp.id).where(GlobalMcp.name == name))) is not None


def _cfg_to_mcp_columns(cfg: dict) -> dict:
    """Frontend cfg (args list, env/headers dicts) -> UserMcp column values (text).
    Secrets in MCP env are kept as ``${VAR}`` references — the real value lives in
    .env (os.environ) and is expanded only when the connection is built."""
    url = str(cfg.get("url") or "").strip()
    command = str(cfg.get("command") or "").strip()
    args, env, headers = cfg.get("args"), cfg.get("env"), cfg.get("headers")
    return {
        "transport": str(cfg.get("transport") or "").strip() or ("http" if url else "stdio"),
        "command": command,
        "url": url,
        "args": "\n".join(str(a) for a in args) if isinstance(args, list) else str(args or ""),
        "env": "\n".join(f"{k}={v}" for k, v in env.items()) if isinstance(env, dict) else str(env or ""),
        "headers": "\n".join(f"{k}={v}" for k, v in headers.items()) if isinstance(headers, dict) else str(headers or ""),
    }


async def save_user_mcp(settings, user_id, name, cfg) -> dict:
    name = (name or "").strip()
    if not _valid_name(name):
        return {"ok": False, "error": "invalid server name"}
    if await _is_global_mcp(name):
        return {"ok": False, "error": f"'{name}' is a global (read-only) server"}
    if not isinstance(cfg, dict) or not (cfg.get("command") or cfg.get("url")):
        return {"ok": False, "error": "server needs a 'command' (stdio) or 'url' (http)"}
    cols = _cfg_to_mcp_columns(cfg)
    async with db_session() as s:
        row = await s.scalar(
            select(UserMcp).where(UserMcp.user_id == str(user_id), UserMcp.name == name)
        )
        if row is None:
            row = UserMcp(user_id=str(user_id), name=name)
            s.add(row)
        for k, v in cols.items():
            setattr(row, k, v)
        if "enabled" in cfg:
            row.is_active = bool(cfg["enabled"])
    _invalidate_user_cache(user_id)
    return {"ok": True, "name": name}


async def delete_user_mcp(settings, user_id, name) -> dict:
    name = (name or "").strip()
    if await _is_global_mcp(name):
        return {"ok": False, "error": f"'{name}' is a global (read-only) server"}
    async with db_session() as s:
        res = await s.execute(
            sa_delete(UserMcp).where(UserMcp.user_id == str(user_id), UserMcp.name == name)
        )
        existed = (res.rowcount or 0) > 0
    if existed:
        _invalidate_user_cache(user_id)
    return {"ok": existed, "name": name}


async def toggle_user_mcp(settings, user_id, name, enabled) -> dict:
    name = (name or "").strip()
    if await _is_global_mcp(name):
        return {"ok": False, "error": f"'{name}' is a global (read-only) server"}
    async with db_session() as s:
        row = await s.scalar(
            select(UserMcp).where(UserMcp.user_id == str(user_id), UserMcp.name == name)
        )
        if row is None:
            return {"ok": False, "error": f"server '{name}' not found"}
        row.is_active = bool(enabled)
    _invalidate_user_cache(user_id)
    return {"ok": True, "name": name, "enabled": bool(enabled)}
