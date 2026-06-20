"""Deep agent factory + invocation helpers.

One compiled agent per ``(kind, user, model)``. Per-user isolation is via the
store namespace ``(user_id, "fs")`` + the LangGraph ``thread_id``.

Capabilities loaded on demand by the agent:
  * **Skills** — ``/skills/global/`` (read-only, shared, from disk) + ``/skills/user/``
    (per-user store). Runtime-loaded; no recompile when a user adds a skill.
  * **MCP plugins** — global (``config/global.mcp.json``) + per-user
    (``data/users/<uid>/mcp.json``) loaded as tools. In run mode, every MCP/plugin
    tool is gated for human approval (plus any ``JOYJOY_INTERRUPT_TOOLS`` built-ins).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, FilesystemBackend, StoreBackend
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langchain_openai import AzureChatOpenAI
from langgraph.store.base import BaseStore

from .config import Settings
from .context import AgentContext

logger = logging.getLogger("joyjoy.agent")

DEFAULT_SYSTEM_PROMPT = (
    "You are joyjoy, a helpful AI assistant running as a multi-tenant deep agent. "
    "Each user has a private, isolated workspace, long-term memory, and skills. "
    "Use your filesystem and memory tools to keep durable, per-user context, and use "
    "your skills and plugin tools when they help."
)

# Skill sources the agent reads on demand: read-only global (shared) + per-user.
SKILL_SOURCES = ["/skills/global/", "/skills/user/"]

# (kind, user_id, model_id) -> compiled deep agent
_AGENT_CACHE: dict[tuple, object] = {}


def build_model_for(settings: Settings, model_id: str, uid: str | None = None) -> BaseChatModel:
    """Chat model for a registry model id, dispatched by ``spec['provider']``.

    Supported providers:
      * ``azure_openai`` (default) — ``AzureChatOpenAI`` (o4-mini/o3/gpt-5/gpt-4.1).
      * ``anthropic`` — ``ChatAnthropic``; works against api.anthropic.com and
        Azure AI Foundry's ``/anthropic`` Claude endpoint (set ``endpoint`` to it).
      * ``bedrock`` — ``ChatBedrockConverse``; AWS creds/region resolve via the
        standard boto3 chain (env ``AWS_*`` / instance role) unless given in spec.
      * ``openai`` — ``ChatOpenAI`` against any OpenAI-compatible endpoint
        (OpenAI / OpenRouter / DeepSeek / Groq / local) via optional ``endpoint``.
      * ``gemini`` — ``ChatGoogleGenerativeAI`` (Google AI Studio API key).

    Provider SDKs are imported lazily so a missing optional package (e.g.
    langchain-aws / langchain-google-genai) never breaks the installed providers.
    """
    specs = merged_model_specs(settings, uid)
    spec = specs.get(model_id) or specs.get(settings.default_model) or next(iter(specs.values()))
    provider = (spec.get("provider") or "azure_openai").lower()

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=spec["deployment"],
            api_key=spec["api_key"],
            base_url=spec["endpoint"] or None,
            max_tokens=spec.get("max_tokens") or 4096,
            streaming=True,
        )

    if provider == "bedrock":
        from langchain_aws import ChatBedrockConverse

        kwargs: dict = {"model": spec["deployment"]}
        if spec.get("region"):
            kwargs["region_name"] = spec["region"]
        if spec.get("max_tokens"):
            kwargs["max_tokens"] = spec["max_tokens"]
        # Static keys are optional — boto3 also resolves env/instance-role creds.
        # Per-model creds (entered in the Providers tab) win; else boto3 env/role chain.
        ak = spec.get("aws_access_key_id") or os.environ.get("AWS_ACCESS_KEY_ID")
        sk = spec.get("aws_secret_access_key") or os.environ.get("AWS_SECRET_ACCESS_KEY")
        if ak and sk:
            kwargs["aws_access_key_id"] = ak
            kwargs["aws_secret_access_key"] = sk
            st = spec.get("aws_session_token") or os.environ.get("AWS_SESSION_TOKEN")
            if st:
                kwargs["aws_session_token"] = st
        return ChatBedrockConverse(**kwargs)

    if provider in ("openai", "openai_compatible"):
        # Any OpenAI-compatible endpoint: OpenAI, OpenRouter, DeepSeek, Groq,
        # Together, vLLM/Ollama, etc. Omit endpoint => api.openai.com.
        from langchain_openai import ChatOpenAI

        kwargs = {"model": spec["deployment"], "api_key": spec["api_key"], "streaming": True}
        if spec.get("endpoint"):
            kwargs["base_url"] = spec["endpoint"]
        if spec.get("max_tokens"):
            kwargs["max_tokens"] = spec["max_tokens"]
        return ChatOpenAI(**kwargs)

    if provider in ("gemini", "google"):
        from langchain_google_genai import ChatGoogleGenerativeAI

        kwargs = {"model": spec["deployment"], "google_api_key": spec["api_key"]}
        if spec.get("max_tokens"):
            kwargs["max_output_tokens"] = spec["max_tokens"]
        return ChatGoogleGenerativeAI(**kwargs)

    # default: Azure OpenAI
    return AzureChatOpenAI(
        azure_endpoint=spec["endpoint"],
        api_key=spec["api_key"],
        api_version=spec["api_version"],
        azure_deployment=spec["deployment"],
        model=spec["id"],
        streaming=True,
    )


def _user_namespace(rt: object) -> tuple[str, ...]:
    """Scope every store operation to the calling user — the isolation boundary."""
    uid = None
    ctx = getattr(rt, "context", None)
    if ctx is not None:
        uid = getattr(ctx, "user_id", None)
        if uid is None and isinstance(ctx, dict):
            uid = ctx.get("user_id")
    if not uid:
        cfg = getattr(rt, "config", None)
        if isinstance(cfg, dict):
            uid = (cfg.get("configurable") or {}).get("user_id")
    return (str(uid or "anonymous"), "fs")


def build_backend(settings: Settings, store: BaseStore, user_id: str = "default"):
    """Composite backend — per-user HOST workspace for the agent's files.

    - default (the agent's working files) → ``FilesystemBackend`` rooted at a real
      per-user host dir ``<user_data_root>/<uid>/workspace`` with
      ``virtual_mode=True`` so every op is confined there (``..``/``~``/absolute
      escapes are blocked). This is the SAME dir the webui workspace panel browses,
      so whatever the agent reads/writes shows up there — and nowhere else.
    - ``/memory/`` and ``/skills/user/`` → per-user ``StoreBackend`` (kept in the
      store so the memory/skills CRUD endpoints stay authoritative).
    - ``/skills/global/`` → read-only global skills from disk (shared by all users).
    """
    user_store = StoreBackend(store=store, namespace=_user_namespace)
    uid = str(user_id or "default")
    host_root = os.path.join(settings.user_data_root, uid, "workspace")
    os.makedirs(host_root, exist_ok=True)
    working_fs = FilesystemBackend(root_dir=host_root, virtual_mode=True)
    routes: dict[str, object] = {
        "/memory/": user_store,
        "/skills/user/": user_store,
    }
    gdir = settings.global_skills_dir
    if gdir and os.path.isdir(gdir):
        routes["/skills/global/"] = FilesystemBackend(root_dir=gdir, virtual_mode=True)
    return CompositeBackend(default=working_fs, routes=routes)


def resolve_model(settings: Settings, requested: str | None, uid: str | None = None) -> str:
    """Return a valid model id for the requested one (or the default), considering
    the user's per-user models merged on top of the global catalog."""
    specs = merged_model_specs(settings, uid)
    if requested and requested in specs:
        return requested
    return settings.default_model if settings.default_model in specs else next(iter(specs))


# ---------------------------------------------------------------------------
# MCP plugins (global + per-user) → tools
# ---------------------------------------------------------------------------
def _parse_mcp_servers(path: str) -> dict:
    try:
        if path and os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            servers = data.get("mcpServers") if isinstance(data, dict) else None
            return servers if isinstance(servers, dict) else {}
    except Exception:
        logger.debug("failed to read mcp config %s", path, exc_info=True)
    return {}


def _expand_env_vars(value):
    """Expand ``${VAR}``/``$VAR`` (from os.environ) in strings / lists / dicts."""
    if isinstance(value, str):
        return os.path.expandvars(value)
    if isinstance(value, list):
        return [_expand_env_vars(v) for v in value]
    if isinstance(value, dict):
        return {k: _expand_env_vars(v) for k, v in value.items()}
    return value


def _to_connections(servers: dict) -> dict:
    """Convert .mcp.json ``mcpServers`` entries to langchain-mcp-adapters connections.

    ``${VAR}`` references in command/args/url/headers/env expand from the process
    env (the backend loads ``.env`` into os.environ at startup), so API keys stay
    out of the config file and only the referenced var reaches the server.
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
            env.update(_expand_env_vars(cfg.get("env") or {}))
            conns[name]["env"] = env
    return conns


def _user_mcp_config_path(settings: Settings, user_id: str) -> str:
    return os.path.join(settings.user_data_root, str(user_id or "default"), "mcp.json")


def _merged_mcp_servers(settings: Settings, user_id: str) -> dict:
    """{name: (cfg, scope)} — global servers first, per-user entries override/extend."""
    merged: dict[str, tuple[dict, str]] = {}
    for name, cfg in _parse_mcp_servers(settings.mcp_global_config).items():
        merged[name] = (cfg, "global")
    for name, cfg in _parse_mcp_servers(_user_mcp_config_path(settings, user_id)).items():
        merged[name] = (cfg, "user")
    return merged


async def load_mcp_tools(settings: Settings, user_id: str) -> list:
    """Load global + per-user MCP tools (user entries override/extend global; disabled
    skipped). Each server is loaded independently so one unreachable provider (e.g. a
    copied-but-not-running server) can't blank out everyone's tools."""
    conns = _to_connections({
        n: cfg for n, (cfg, _s) in _merged_mcp_servers(settings, user_id).items()
        if not (isinstance(cfg, dict) and cfg.get("enabled") is False)
    })
    if not conns:
        return []
    from langchain_mcp_adapters.client import MultiServerMCPClient

    tools: list = []
    for name, conn in conns.items():
        try:
            tools.extend(await asyncio.wait_for(MultiServerMCPClient({name: conn}).get_tools(), timeout=10))
        except Exception:  # noqa: BLE001 - one bad/slow server shouldn't drop the rest (incl. timeout)
            logger.warning("MCP server '%s' failed/timed-out for user=%s (skipped)", name, user_id, exc_info=True)
    logger.info("loaded %d MCP tool(s) for user=%s from servers=%s", len(tools), user_id, list(conns))
    return tools


# ---------------------------------------------------------------------------
# Introspection for the UI: describe MCP servers/tools + skills (global + user)
# ---------------------------------------------------------------------------
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
    for name, (cfg, scope) in _merged_mcp_servers(settings, user_id).items():
        conn = _to_connections({name: cfg})  # expanded — used only to probe
        cfg_d = cfg if isinstance(cfg, dict) else {}
        transport = "http" if cfg_d.get("url") else ("stdio" if cfg_d.get("command") else "unknown")
        enabled = not (cfg_d.get("enabled") is False)
        entry = {
            "name": name,
            "scope": scope,
            "transport": transport,
            "enabled": enabled,
            "status": "configured",
            "tool_count": None,
            # Display the ORIGINAL config (e.g. ${TAVILY_API_KEY} reference), never the
            # expanded secret value or the internal PATH/HOME we inject for the subprocess.
            "command": cfg_d.get("command"),
            "args": cfg_d.get("args") or [],
            "url": cfg_d.get("url"),
            "env": cfg_d.get("env"),
            "headers": cfg_d.get("headers"),
        }
        if not conn:
            entry["status"] = "invalid_config"
            servers_out.append(entry)
            continue
        if not enabled:
            entry["status"] = "disabled"
            servers_out.append(entry)
            continue
        try:
            from langchain_mcp_adapters.client import MultiServerMCPClient

            tls = await asyncio.wait_for(MultiServerMCPClient(conn).get_tools(), timeout=10)
            entry["tool_count"] = len(tls)
            entry["status"] = "active"
            for tl in tls:
                tools_out.append({
                    "name": getattr(tl, "name", ""),
                    "server": name,
                    "scope": scope,
                    "status": "active",  # webui renders this as the tool's status badge
                    "description": getattr(tl, "description", "") or "",
                    "schema_summary": _tool_schema_summary(tl),  # webui reads `schema_summary`
                })
        except Exception:  # noqa: BLE001 - one bad server shouldn't blank the list
            logger.exception("failed to probe MCP server %s for user=%s", name, user_id)
            entry["status"] = "invalid_config"
        servers_out.append(entry)
    return servers_out, tools_out


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


def _parse_skill_md(path: str, fallback_name: str) -> dict:
    """Extract name+description from a SKILL.md file (best-effort)."""
    return _parse_skill_frontmatter(_read_text(path), fallback_name)


async def list_skills(settings: Settings, store: BaseStore | None, user_id: str) -> list[dict]:
    """Global skills (read-only, from disk) + per-user skills (from the store)."""
    skills: list[dict] = []
    gdir = settings.global_skills_dir
    if gdir and os.path.isdir(gdir):
        for entry in sorted(os.listdir(gdir)):
            sd = os.path.join(gdir, entry)
            md = os.path.join(sd, "SKILL.md")
            if os.path.isdir(sd) and os.path.isfile(md):
                meta = _parse_skill_md(md, entry)
                skills.append({**meta, "scope": "global", "editable": False, "enabled": True, "builtin": True})
    # Per-user skills live in the store under /skills/user/<name>/SKILL.md
    # (enabled) or SKILL.md.disabled (toggled off).
    if store is not None:
        try:
            ns = (str(user_id or "default"), "fs")
            items = await store.asearch(ns, limit=1000)
            found: dict[str, dict] = {}
            for it in items or []:
                key = str(getattr(it, "key", "") or "").replace("\\", "/")
                if "/skills/user/" not in key:
                    continue
                low = key.lower()
                if not (low.endswith("/skill.md") or low.endswith("/skill.md.disabled")):
                    continue
                sname = key.split("/skills/user/", 1)[1].split("/", 1)[0]
                if not sname:
                    continue
                en = not low.endswith(".disabled")
                desc = _parse_skill_frontmatter(_store_item_text(it), sname).get("description", "")
                if sname not in found or en:  # prefer the enabled record
                    found[sname] = {"name": sname, "description": desc, "scope": "user", "editable": True, "enabled": en}
            skills.extend(found.values())
        except Exception:  # noqa: BLE001 - store layout varies; never break the global list
            logger.debug("user-skill store listing failed for user=%s", user_id, exc_info=True)
    return skills


def _read_text(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except Exception:  # noqa: BLE001
        logger.debug("failed to read %s", path, exc_info=True)
        return ""


def _safe_skill_dir(root: str, name: str) -> str | None:
    """Resolve <root>/<name> ensuring it stays within root (no traversal)."""
    if not name or any(c in name for c in ("/", "\\")) or ".." in name:
        return None
    root_real = os.path.realpath(root)
    p = os.path.realpath(os.path.join(root_real, name))
    if p != root_real and not p.startswith(root_real + os.sep):
        return None
    return p


async def read_skill_content(settings: Settings, store: BaseStore | None, user_id: str, name: str, file: str | None = None) -> dict:
    """Read a global skill's SKILL.md (read-only) or a linked file, for the UI viewer.

    Returns the webui skill-view shape: ``{success, name, content, linked_files}``
    on success, or ``{success: False, error}`` when not found.
    """
    if not name:
        return {"success": False, "error": "name required"}
    gdir = settings.global_skills_dir
    if gdir and os.path.isdir(gdir):
        sdir = _safe_skill_dir(gdir, name)
        if sdir and os.path.isdir(sdir):
            if file:
                target = _safe_skill_dir(sdir, file) if "/" not in file and "\\" not in file else os.path.realpath(os.path.join(sdir, file))
                if not target or os.path.commonpath([target, os.path.realpath(sdir)]) != os.path.realpath(sdir) or not os.path.isfile(target):
                    return {"success": False, "error": "File not found"}
                return {"success": True, "name": name, "content": _read_text(target), "path": file}
            md = os.path.join(sdir, "SKILL.md")
            if os.path.isfile(md):
                linked: dict[str, bool] = {}
                for root, _dirs, files in os.walk(sdir):
                    for fn in files:
                        rel = os.path.relpath(os.path.join(root, fn), sdir).replace("\\", "/")
                        if rel != "SKILL.md":
                            linked[rel] = True
                return {
                    "success": True, "name": name, "scope": "global", "editable": False,
                    "content": _read_text(md), "linked_files": linked,
                }
    # Per-user skill from the store (read-only view; created/edited via the UI).
    if store is not None:
        try:
            ns = (str(user_id or "default"), "fs")
            for suffix in ("SKILL.md", "SKILL.md.disabled"):
                item = await store.aget(ns, f"/skills/user/{name}/{suffix}")
                if item is not None:
                    return {
                        "success": True, "name": name, "scope": "user", "editable": True,
                        "enabled": suffix == "SKILL.md", "content": _store_item_text(item), "linked_files": {},
                    }
        except Exception:  # noqa: BLE001
            logger.debug("user-skill content read failed for %s", name, exc_info=True)
    return {"success": False, "error": f"Skill '{name}' not found.", "available_skills": [], "linked_files": {}}


# ---------------------------------------------------------------------------
# CRUD: per-user skills (store) + per-user MCP (mcp.json) + per-user memory.
# Global skills/MCP are READ-ONLY here — writes only ever touch the user's space.
# ---------------------------------------------------------------------------
def _store_item_text(item) -> str:
    """Extract file text from a StoreBackend store Item (v1 list / v2 str)."""
    v = getattr(item, "value", None) if item is not None else None
    if isinstance(v, dict):
        c = v.get("content")
        if isinstance(c, list):
            return "\n".join(str(x) for x in c)
        if isinstance(c, str):
            return c
    return ""


def _user_store_backend(store: BaseStore, user_id: str):
    """A StoreBackend bound to the user's namespace, usable outside a graph run."""
    ns = (str(user_id or "default"), "fs")
    return StoreBackend(store=store, namespace=lambda _rt: ns), ns


def _valid_name(name: str) -> bool:
    return bool(name) and not any(c in name for c in ("/", "\\")) and ".." not in name


def _invalidate_user_cache(user_id: str) -> None:
    """Drop cached agents for a user so skill/MCP/memory edits take effect next call."""
    uid = str(user_id or "default")
    for k in [k for k in _AGENT_CACHE if isinstance(k, tuple) and len(k) >= 2 and k[1] == uid]:
        _AGENT_CACHE.pop(k, None)


def _file_store_value(sb, content: str) -> dict:
    """Serialize content into the StoreBackend's on-store value format."""
    from deepagents.backends.store import create_file_data

    return sb._convert_file_data_to_store_value(create_file_data(content or ""))


async def save_user_skill(store, user_id, name, content) -> dict:
    """Create or overwrite a per-user skill's SKILL.md in the store (enables it)."""
    name = (name or "").strip()
    if not _valid_name(name):
        return {"ok": False, "error": "invalid skill name"}
    sb, ns = _user_store_backend(store, user_id)
    path = f"/skills/user/{name}/SKILL.md"
    await store.aput(ns, path, _file_store_value(sb, content or ""))
    try:  # writing a fresh SKILL.md clears any disabled twin
        await store.adelete(ns, path + ".disabled")
    except Exception:  # noqa: BLE001
        pass
    _invalidate_user_cache(user_id)
    return {"ok": True, "name": name, "path": path}


async def delete_user_skill(store, user_id, name) -> dict:
    name = (name or "").strip()
    if not _valid_name(name):
        return {"ok": False, "error": "invalid skill name"}
    _sb, ns = _user_store_backend(store, user_id)
    prefix = f"/skills/user/{name}/"
    deleted = 0
    try:
        items = await store.asearch(ns, limit=1000)
        for it in items or []:
            k = str(getattr(it, "key", "") or "")
            if k.replace("\\", "/").startswith(prefix):
                await store.adelete(ns, k)
                deleted += 1
    except Exception:  # noqa: BLE001
        logger.exception("delete_user_skill failed user=%s name=%s", user_id, name)
        return {"ok": False, "error": "delete failed"}
    _invalidate_user_cache(user_id)
    return {"ok": deleted > 0, "name": name, "deleted": deleted}


async def toggle_user_skill(store, user_id, name, enabled) -> dict:
    """Enable/disable a user skill by renaming SKILL.md <-> SKILL.md.disabled."""
    name = (name or "").strip()
    if not _valid_name(name):
        return {"ok": False, "error": "invalid skill name"}
    _sb, ns = _user_store_backend(store, user_id)
    on = f"/skills/user/{name}/SKILL.md"
    off = on + ".disabled"
    src, dst = (off, on) if enabled else (on, off)
    item = await store.aget(ns, src)
    if item is not None:
        await store.aput(ns, dst, getattr(item, "value"))
        await store.adelete(ns, src)
    _invalidate_user_cache(user_id)
    return {"ok": True, "name": name, "enabled": bool(enabled)}


# ---- per-user MCP CRUD (data/users/<uid>/mcp.json; global is read-only) ----
def _read_user_mcp_servers(settings, user_id) -> dict:
    return _parse_mcp_servers(_user_mcp_config_path(settings, user_id))


def _write_user_mcp_servers(settings, user_id, servers: dict) -> None:
    path = _user_mcp_config_path(settings, user_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"mcpServers": servers}, f, indent=2)
    os.replace(tmp, path)


def _is_global_mcp(settings, name) -> bool:
    return name in _parse_mcp_servers(settings.mcp_global_config)


def save_user_mcp(settings, user_id, name, cfg) -> dict:
    name = (name or "").strip()
    if not _valid_name(name):
        return {"ok": False, "error": "invalid server name"}
    if _is_global_mcp(settings, name):
        return {"ok": False, "error": f"'{name}' is a global (read-only) server"}
    if not isinstance(cfg, dict) or not (cfg.get("command") or cfg.get("url")):
        return {"ok": False, "error": "server needs a 'command' (stdio) or 'url' (http)"}
    servers = _read_user_mcp_servers(settings, user_id)
    servers[name] = {k: v for k, v in cfg.items() if v not in (None, "")}
    _write_user_mcp_servers(settings, user_id, servers)
    _invalidate_user_cache(user_id)
    return {"ok": True, "name": name}


def delete_user_mcp(settings, user_id, name) -> dict:
    name = (name or "").strip()
    if _is_global_mcp(settings, name):
        return {"ok": False, "error": f"'{name}' is a global (read-only) server"}
    servers = _read_user_mcp_servers(settings, user_id)
    existed = servers.pop(name, None) is not None
    if existed:
        _write_user_mcp_servers(settings, user_id, servers)
        _invalidate_user_cache(user_id)
    return {"ok": existed, "name": name}


def toggle_user_mcp(settings, user_id, name, enabled) -> dict:
    name = (name or "").strip()
    if _is_global_mcp(settings, name):
        return {"ok": False, "error": f"'{name}' is a global (read-only) server"}
    servers = _read_user_mcp_servers(settings, user_id)
    if name not in servers or not isinstance(servers[name], dict):
        return {"ok": False, "error": f"server '{name}' not found"}
    servers[name]["enabled"] = bool(enabled)
    _write_user_mcp_servers(settings, user_id, servers)
    _invalidate_user_cache(user_id)
    return {"ok": True, "name": name, "enabled": bool(enabled)}


# ---- per-user model catalog CRUD (data/users/<uid>/models.json; global is read-only) ----
_VALID_PROVIDERS = {"azure_openai", "anthropic", "bedrock", "openai", "gemini"}

# Field schema per provider — drives the Providers-tab add/edit form in the UI.
PROVIDER_TYPES = [
    {
        "id": "azure_openai",
        "label": "Azure OpenAI",
        "fields": [
            {"key": "id", "label": "Model ID", "required": True, "placeholder": "e.g. o4-mini"},
            {"key": "deployment", "label": "Deployment name", "required": True, "placeholder": "Azure deployment"},
            {"key": "endpoint", "label": "Endpoint URL", "required": True, "placeholder": "https://<res>.openai.azure.com"},
            {"key": "api_version", "label": "API version", "required": True, "placeholder": "2024-12-01-preview"},
            {"key": "api_key", "label": "API key", "required": True, "secret": True},
        ],
    },
    {
        "id": "anthropic",
        "label": "Azure AI Foundry / Anthropic (Claude)",
        "fields": [
            {"key": "id", "label": "Model ID", "required": True, "placeholder": "e.g. claude-opus-4-7"},
            {"key": "deployment", "label": "Model name", "required": True, "placeholder": "claude-opus-4-7"},
            {"key": "endpoint", "label": "Base URL", "required": True, "placeholder": "https://<res>.services.ai.azure.com/anthropic"},
            {"key": "api_key", "label": "API key", "required": True, "secret": True},
            {"key": "max_tokens", "label": "Max tokens", "required": False, "placeholder": "4096"},
        ],
    },
    {
        "id": "bedrock",
        "label": "Amazon Bedrock",
        "fields": [
            {"key": "id", "label": "Model ID", "required": True, "placeholder": "e.g. claude-sonnet-bedrock"},
            {"key": "deployment", "label": "Bedrock model id", "required": True, "placeholder": "us.anthropic.claude-3-7-sonnet-20250219-v1:0"},
            {"key": "region", "label": "AWS region", "required": True, "placeholder": "us-east-1"},
            {"key": "aws_access_key_id", "label": "AWS access key id", "required": False},
            {"key": "aws_secret_access_key", "label": "AWS secret access key", "required": False, "secret": True},
            {"key": "max_tokens", "label": "Max tokens", "required": False, "placeholder": "4096"},
        ],
    },
    {
        "id": "openai",
        "label": "OpenAI-compatible (OpenAI / OpenRouter / DeepSeek / Groq / local)",
        "fields": [
            {"key": "id", "label": "Model ID", "required": True, "placeholder": "e.g. gpt-4o or openrouter-claude"},
            {"key": "deployment", "label": "Model name", "required": True, "placeholder": "gpt-4o"},
            {"key": "endpoint", "label": "Base URL (blank = api.openai.com)", "required": False, "placeholder": "https://openrouter.ai/api/v1"},
            {"key": "api_key", "label": "API key", "required": True, "secret": True},
            {"key": "max_tokens", "label": "Max tokens", "required": False, "placeholder": "(optional)"},
        ],
    },
    {
        "id": "gemini",
        "label": "Google Gemini",
        "fields": [
            {"key": "id", "label": "Model ID", "required": True, "placeholder": "e.g. gemini-2.0-flash"},
            {"key": "deployment", "label": "Model name", "required": True, "placeholder": "gemini-2.0-flash"},
            {"key": "api_key", "label": "API key (Google AI Studio)", "required": True, "secret": True},
            {"key": "max_tokens", "label": "Max output tokens", "required": False, "placeholder": "(optional)"},
        ],
    },
]

_SECRET_FIELDS = ("api_key", "aws_secret_access_key", "aws_session_token")
_MASK = "••••"  # ••••


def _user_models_path(settings: Settings, user_id: str) -> str:
    return os.path.join(settings.user_data_root, str(user_id or "default"), "models.json")


def read_user_models(settings, user_id) -> list[dict]:
    """Per-user model entries (raw, unnormalized) from data/users/<uid>/models.json."""
    path = _user_models_path(settings, user_id)
    try:
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            models = data.get("models") if isinstance(data, dict) else data
            return models if isinstance(models, list) else []
    except Exception:
        logger.debug("read_user_models failed user=%s", user_id, exc_info=True)
    return []


def _write_user_models(settings, user_id, models: list) -> None:
    path = _user_models_path(settings, user_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"models": models}, f, indent=2)
    os.replace(tmp, path)


def merged_model_specs(settings: Settings, user_id: str | None = None) -> dict[str, dict]:
    """Global catalog (config/models.json or env) + the user's own models on top."""
    specs = dict(settings.model_specs)  # global
    for m in read_user_models(settings, user_id):
        s = settings.normalize_model(m)
        if s:
            specs[s["id"]] = s  # a user entry adds to / overrides the catalog
    return specs


def _is_global_model(settings, mid) -> bool:
    return mid in settings.model_specs


def _mask_key(k) -> str:
    k = str(k or "")
    return (_MASK + k[-4:]) if len(k) > 4 else ("" if not k else _MASK)


def _public_model_spec(s: dict) -> dict:
    """UI-safe view of a spec — never returns raw secrets, only masks/flags."""
    return {
        "id": s.get("id"),
        "provider": s.get("provider"),
        "deployment": s.get("deployment"),
        "endpoint": s.get("endpoint"),
        "api_version": s.get("api_version"),
        "region": s.get("region"),
        "max_tokens": s.get("max_tokens") or 0,
        "aws_access_key_id": s.get("aws_access_key_id") or "",
        "has_key": bool(s.get("api_key")),
        "api_key_masked": _mask_key(s.get("api_key")),
        "has_aws_secret": bool(s.get("aws_secret_access_key")),
    }


def describe_models(settings: Settings, user_id: str) -> list[dict]:
    """Global (read-only) + per-user models for the Providers tab; keys masked."""
    out = []
    for _mid, s in settings.model_specs.items():
        out.append({**_public_model_spec(s), "scope": "global", "editable": False})
    for m in read_user_models(settings, user_id):
        s = settings.normalize_model(m)
        if s:
            out.append({**_public_model_spec(s), "scope": "user", "editable": True})
    return out


def _validate_model_entry(e: dict) -> str | None:
    p = e["provider"]
    if p in ("azure_openai", "anthropic"):
        if not e.get("endpoint"):
            return "endpoint / URL is required"
        if not e.get("api_key"):
            return "api_key is required"
    if p == "azure_openai" and not e.get("api_version"):
        return "api_version is required for Azure OpenAI"
    if p == "bedrock" and not e.get("deployment"):
        return "Bedrock model id (deployment) is required"
    if p in ("openai", "gemini"):
        if not e.get("deployment"):
            return "model name (deployment) is required"
        if not e.get("api_key"):
            return "api_key is required"
    return None


def save_user_model(settings, user_id, raw: dict) -> dict:
    """Create/update a per-user model. Secrets left blank/masked keep the old value."""
    raw = raw or {}
    mid = str(raw.get("id") or "").strip()
    if not _valid_name(mid):
        return {"ok": False, "error": "invalid model id"}
    if _is_global_model(settings, mid):
        return {"ok": False, "error": f"'{mid}' is a global (read-only) model"}
    provider = str(raw.get("provider") or "azure_openai").strip().lower()
    if provider not in _VALID_PROVIDERS:
        return {"ok": False, "error": "provider must be azure_openai | anthropic | bedrock"}
    models = read_user_models(settings, user_id)
    existing = next((m for m in models if str(m.get("id")) == mid), None)
    entry: dict = {"id": mid, "provider": provider}
    for k in ("deployment", "endpoint", "api_version", "region", "aws_access_key_id"):
        v = raw.get(k)
        if v not in (None, ""):
            entry[k] = str(v).strip()
    mt = raw.get("max_tokens")
    if mt not in (None, ""):
        try:
            entry["max_tokens"] = int(mt)
        except (TypeError, ValueError):
            pass
    # Secrets: accept only a fresh value; blank or the masked placeholder keeps the old one.
    for sk in _SECRET_FIELDS:
        v = str(raw.get(sk) or "").strip()
        if v and not v.startswith(_MASK):
            entry[sk] = v
        elif existing and existing.get(sk):
            entry[sk] = existing.get(sk)
    err = _validate_model_entry(entry)
    if err:
        return {"ok": False, "error": err}
    models = [m for m in models if str(m.get("id")) != mid] + [entry]
    _write_user_models(settings, user_id, models)
    _invalidate_user_cache(user_id)
    return {"ok": True, "id": mid}


def delete_user_model(settings, user_id, mid) -> dict:
    mid = str(mid or "").strip()
    if _is_global_model(settings, mid):
        return {"ok": False, "error": f"'{mid}' is a global (read-only) model"}
    models = read_user_models(settings, user_id)
    new = [m for m in models if str(m.get("id")) != mid]
    existed = len(new) != len(models)
    if existed:
        _write_user_models(settings, user_id, new)
        _invalidate_user_cache(user_id)
    return {"ok": existed, "id": mid}


# ---- per-user memory docs (notes / profile / soul), stored per user ----
MEMORY_FILES = {"memory": "/memory/MEMORY.md", "user": "/memory/USER.md", "soul": "/memory/SOUL.md"}


async def read_memory(store, user_id) -> dict:
    """Return {memory, user, soul} text for a user (empty strings if unset)."""
    out = {k: "" for k in MEMORY_FILES}
    if store is None:
        return out
    _sb, ns = _user_store_backend(store, user_id)
    for sec, path in MEMORY_FILES.items():
        try:
            out[sec] = _store_item_text(await store.aget(ns, path))
        except Exception:  # noqa: BLE001
            logger.debug("read_memory %s failed", sec, exc_info=True)
    return out


async def write_memory(store, user_id, section, content) -> dict:
    if section not in MEMORY_FILES:
        return {"ok": False, "error": "section must be memory|user|soul"}
    sb, ns = _user_store_backend(store, user_id)
    await store.aput(ns, MEMORY_FILES[section], _file_store_value(sb, content or ""))
    _invalidate_user_cache(user_id)  # soul/profile/notes feed the system prompt
    return {"ok": True, "section": section}


async def _system_prompt_for(store, user_id) -> str:
    """Base prompt + the user's soul/profile/notes so memory actually shapes the agent."""
    base = DEFAULT_SYSTEM_PROMPT
    try:
        mem = await read_memory(store, user_id)
    except Exception:  # noqa: BLE001
        return base
    parts = []
    if (mem.get("soul") or "").strip():
        parts.append("## Your persona (agent soul)\n" + mem["soul"].strip())
    if (mem.get("user") or "").strip():
        parts.append("## About the user\n" + mem["user"].strip())
    if (mem.get("memory") or "").strip():
        parts.append("## Long-term notes to remember\n" + mem["memory"].strip())
    return base + "\n\n" + "\n\n".join(parts) if parts else base


async def _get_or_build(settings, checkpointer, store, model_id, user_id, *, run_mode):
    uid = str(user_id or "default")
    mid = resolve_model(settings, model_id, uid)
    key = ("run" if run_mode else "chat", uid, mid)
    agent = _AGENT_CACHE.get(key)
    if agent is not None:
        return agent
    mcp_tools = await load_mcp_tools(settings, uid)
    system_prompt = await _system_prompt_for(store, uid)
    interrupt_on = None
    if run_mode:
        # Approval policy: gate all MCP/plugin tools, plus any configured built-ins.
        gated = {t.strip() for t in (settings.interrupt_tools or "").split(",") if t.strip()}
        gated |= {getattr(t, "name", None) for t in mcp_tools if getattr(t, "name", None)}
        interrupt_on = {t: True for t in gated if t} or None
    agent = create_deep_agent(
        model=build_model_for(settings, mid, uid),
        tools=mcp_tools,
        system_prompt=system_prompt,
        backend=build_backend(settings, store, uid),
        checkpointer=checkpointer,
        store=store,
        context_schema=AgentContext,
        interrupt_on=interrupt_on,
        skills=SKILL_SOURCES,
    )
    _AGENT_CACHE[key] = agent
    logger.info(
        "compiled %s agent user=%s model=%s mcp_tools=%d gated=%s",
        "run" if run_mode else "chat", uid, mid, len(mcp_tools), list(interrupt_on or {}),
    )
    return agent


async def get_agent(settings, checkpointer, store, model_id=None, user_id="default"):
    """Streaming/chat agent (no approval gating)."""
    return await _get_or_build(settings, checkpointer, store, model_id, user_id, run_mode=False)


async def get_run_agent(settings, checkpointer, store, model_id=None, user_id="default"):
    """Runs-API agent (MCP/plugin tools gated for HITL approval)."""
    return await _get_or_build(settings, checkpointer, store, model_id, user_id, run_mode=True)


# ----------------------------------------------------------------------------
# Invocation helpers — defensive about the langgraph runtime ``context=`` kwarg.
# ----------------------------------------------------------------------------
def _config_for(ctx: AgentContext) -> dict:
    return {"configurable": {"thread_id": ctx.thread_id or "default", "user_id": ctx.user_id}}


def stream_messages(agent, text: str, ctx: AgentContext):
    payload = {"messages": [HumanMessage(text)]}
    config = _config_for(ctx)
    try:
        return agent.astream(payload, config=config, context=ctx, stream_mode="messages")
    except TypeError:
        return agent.astream(payload, config=config, stream_mode="messages")


async def invoke_once(agent, text: str, ctx: AgentContext) -> str:
    payload = {"messages": [HumanMessage(text)]}
    config = _config_for(ctx)
    try:
        result = await agent.ainvoke(payload, config=config, context=ctx)
    except TypeError:
        result = await agent.ainvoke(payload, config=config)
    return last_ai_text(result)


def last_ai_text(result: dict) -> str:
    for m in reversed((result or {}).get("messages") or []):
        if isinstance(m, AIMessage):
            return _content_to_text(m.content)
    return ""


def chunk_text(chunk: object) -> str:
    if not isinstance(chunk, AIMessageChunk):
        return ""
    return _content_to_text(getattr(chunk, "content", ""))


def _content_to_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") in (None, "text") and isinstance(block.get("text"), str):
                    parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return ""
