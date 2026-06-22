"""Deep agent factory + invocation helpers.

One compiled agent per ``(kind, user, model)``. Per-user isolation is via the
store namespace ``(user_id, "fs")`` + the LangGraph ``thread_id``.

Capabilities loaded on demand by the agent — all DB-backed (served via ``dbfs``):
  * **Skills** — ``/skills/global/`` (shipped, read-only) + ``/skills/user/`` (per-user,
    authored in the Skills tab), both from the DB. Runtime-loaded; no recompile.
  * **MCP plugins** — global (``global_mcps``) + per-user (``user_mcps``) loaded as
    tools. In run mode, every MCP/plugin tool is gated for human approval (plus any
    ``JOYJOY_INTERRUPT_TOOLS`` built-ins).
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import os
import re
import zipfile
from pathlib import Path

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, FilesystemBackend, StoreBackend
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langchain_openai import AzureChatOpenAI
from langgraph.runtime import get_runtime

from sqlalchemy import delete as sa_delete
from sqlalchemy import select

from .config import Settings
from .context import AgentContext
from .db import db_session, decrypt_secrets, encrypt
from .db.models import (
    GlobalMcp,
    GlobalModel,
    GlobalProvider,
    GlobalSkill,
    SkillFile,
    UserConfig,
    UserMcp,
    UserModel,
    UserSkill,
)
from .dbfs import DbSkillsBackend, MemoryBackend, _file_text

logger = logging.getLogger("joyjoy.agent")

DEFAULT_SYSTEM_PROMPT = (
    "You are joyjoy, a helpful AI assistant running as a multi-tenant deep agent. "
    "Each user has a private, isolated workspace, long-term memory, and skills. "
    "Use your filesystem and memory tools to keep durable, per-user context, and use "
    "your skills and plugin tools when they help.\n\n"
    "Memory layout:\n"
    "- `/memory/AGENTS.md` — your core long-term memory; it is ALWAYS loaded into "
    "your context. Keep it concise; update it with `edit_file` for durable, "
    "frequently-needed facts (the user's identity, standing preferences, how to behave).\n"
    "- `/memories/` — a persistent, cross-session folder for everything else. Create "
    "and organize arbitrary files here on demand (e.g. `/memories/<topic>.md`) for "
    "scenario- or project-specific notes that don't need to be in context every turn. "
    "Use `ls`/`glob`/`read_file` to find and load them when relevant, and "
    "`write_file`/`edit_file` to record new ones."
)

# Skill sources the agent reads on demand: read-only global (shared) + per-user.
SKILL_SOURCES = ["/skills/global/", "/skills/user/"]

# (kind, user_id, model_id, reasoning) -> compiled deep agent
_AGENT_CACHE: dict[tuple, object] = {}

# --- Reasoning / extended-thinking support --------------------------------
# Effort level -> Anthropic extended-thinking token budget. Higher = more thinking.
_REASONING_BUDGETS = {"minimal": 1024, "low": 2048, "medium": 4096, "high": 8192, "extra_high": 16384}


def normalize_reasoning_effort(reasoning) -> str | None:
    """Canonical effort key (minimal/low/medium/high/extra_high) or None (= off).

    Accepts bools, the UI labels, OpenAI effort strings, or None.
    """
    if reasoning is None:
        return None
    if isinstance(reasoning, bool):
        return "medium" if reasoning else None
    s = str(reasoning).strip().lower().replace("-", "_").replace(" ", "_")
    if s in ("", "none", "off", "false", "0", "disabled"):
        return None
    if s in ("default", "on", "true", "1", "enabled", "auto"):
        return "medium"
    # UI aliases: the composer effort chip emits "xhigh" for "Extra High".
    s = {"xhigh": "extra_high", "x_high": "extra_high", "extrahigh": "extra_high",
         "extra": "extra_high", "min": "minimal"}.get(s, s)
    if s in _REASONING_BUDGETS:
        return s
    return "medium"


def model_supports_reasoning(spec: dict) -> bool:
    """Can this model produce reasoning / extended thinking? Heuristic by provider +
    model name, override-able via an explicit ``reasoning`` bool on the spec."""
    if isinstance(spec.get("reasoning"), bool):
        return spec["reasoning"]
    provider = (spec.get("provider") or "azure_openai").lower()
    ids = [str(spec.get("deployment") or "").lower(), str(spec.get("id") or "").lower()]
    blob = " ".join(ids)
    if provider == "anthropic":
        return True  # Claude 3.7 / 4.x support extended thinking
    if provider == "bedrock":
        return any(k in blob for k in ("claude-3-7", "claude-opus-4", "claude-sonnet-4", "claude-4"))
    if provider == "azure_openai":
        return any(re.match(r"o[1345]\b", i) for i in ids) or "gpt-5" in blob
    if provider in ("openai", "openai_compatible"):
        return any(k in blob for k in ("o1", "o3", "o4", "deepseek-r", "gpt-5", "reason"))
    if provider in ("gemini", "google"):
        return "2.5" in blob or "thinking" in blob
    return False


async def build_model_for(settings: Settings, model_id: str, uid: str | None = None, reasoning=None) -> BaseChatModel:
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
    specs = await merged_model_specs(settings, uid)
    spec = specs.get(model_id) or specs.get(settings.default_model) or next(iter(specs.values()))
    provider = (spec.get("provider") or "azure_openai").lower()
    effort = normalize_reasoning_effort(reasoning) if model_supports_reasoning(spec) else None

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        anthropic_kwargs = dict(
            model=spec["deployment"],
            api_key=spec["api_key"],
            base_url=spec["endpoint"] or None,
            max_tokens=spec.get("max_tokens") or 4096,
            streaming=True,
        )
        if effort:
            ep = (spec.get("endpoint") or "").lower()
            if "azure" in ep or "foundry" in ep:
                # Azure AI Foundry Claude uses ADAPTIVE thinking (it rejects the standard
                # {"type":"enabled","budget_tokens":N}). NOTE: Foundry returns only a thinking
                # *signature*, not the thinking *text* — the model reasons but the text is
                # redacted (so no visible thinking rows). Standard Anthropic / DeepSeek-R1 DO
                # return reasoning text, which runs.py forwards as reasoning.available events.
                anthropic_kwargs["max_tokens"] = max(int(spec.get("max_tokens") or 4096), 8192)
                anthropic_kwargs["thinking"] = {"type": "adaptive"}
            else:
                # Standard Anthropic API (api.anthropic.com): explicit thinking budget.
                budget = _REASONING_BUDGETS.get(effort, 4096)
                anthropic_kwargs["max_tokens"] = max(int(spec.get("max_tokens") or 4096), budget + 1024)
                anthropic_kwargs["thinking"] = {"type": "enabled", "budget_tokens": budget}
        return ChatAnthropic(**anthropic_kwargs)

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
        if effort:
            kwargs["reasoning_effort"] = "high" if effort in ("high", "extra_high") else ("low" if effort in ("minimal", "low") else "medium")
        return ChatOpenAI(**kwargs)

    if provider in ("gemini", "google"):
        from langchain_google_genai import ChatGoogleGenerativeAI

        kwargs = {"model": spec["deployment"], "google_api_key": spec["api_key"]}
        if spec.get("max_tokens"):
            kwargs["max_output_tokens"] = spec["max_tokens"]
        return ChatGoogleGenerativeAI(**kwargs)

    # default: Azure OpenAI
    azure_kwargs = dict(
        azure_endpoint=spec["endpoint"],
        api_key=spec["api_key"],
        api_version=spec["api_version"],
        azure_deployment=spec["deployment"],
        model=spec["id"],
        streaming=True,
    )
    if effort:
        # o-series / gpt-5 accept reasoning_effort low|medium|high. ("minimal" is gpt-5-only
        # and o3/o4-mini reject it, so map minimal→low for safety; extra_high→high.) Azure
        # usually hides the reasoning *text*, so thinking rows stay empty — the effort still applies.
        azure_kwargs["reasoning_effort"] = (
            "high" if effort in ("high", "extra_high")
            else "medium" if effort == "medium"
            else "low"
        )
    return AzureChatOpenAI(**azure_kwargs)


def _session_workspace_seg() -> str | None:
    """The current session's workspace key from the runtime context
    (``workspace_id`` or ``thread_id``), or None when called outside a run."""
    try:
        rt = get_runtime()
    except Exception:
        return None
    ctx = getattr(rt, "context", None)
    seg = getattr(ctx, "workspace_id", None) or getattr(ctx, "thread_id", None)
    if not seg:
        cfg = getattr(rt, "config", None)
        conf = cfg.get("configurable", {}) if isinstance(cfg, dict) else {}
        seg = conf.get("workspace_id") or conf.get("thread_id")
    if not seg:
        return None
    seg = re.sub(r"[^A-Za-z0-9._-]", "_", str(seg))[:128]
    return seg or None


class SessionFilesystemBackend(FilesystemBackend):
    """A ``FilesystemBackend`` whose root is ``<base>/<session>`` — resolved PER
    OPERATION from the runtime (``workspace_id`` or ``thread_id``). Each chat thus
    gets its own working dir, while ``/memory`` and ``/skills`` stay user-scoped.
    Forked chats share a ``workspace_id`` → the same dir. One cached agent (per
    user/model) still serves every session: the root is computed at file-op time,
    not at construction."""

    @property
    def cwd(self) -> Path:
        seg = _session_workspace_seg()
        root = (self._base / seg) if seg else self._base
        try:
            root.mkdir(parents=True, exist_ok=True)
        except OSError:
            logger.debug("workspace mkdir failed: %s", root, exc_info=True)
        return root

    @cwd.setter
    def cwd(self, value) -> None:
        # FilesystemBackend.__init__ assigns self.cwd = root_dir; capture it as the
        # per-user base, then the getter appends the per-session segment.
        self._base = Path(value).resolve() if value else Path.cwd()


def build_backend(settings: Settings, user_id: str = "default"):
    """Composite backend — per-user HOST workspace for the agent's files.

    - default (the agent's working files) → ``FilesystemBackend`` rooted at a real
      per-user host dir ``<user_data_root>/<uid>/workspace`` with
      ``virtual_mode=True`` so every op is confined there (``..``/``~``/absolute
      escapes are blocked). This is the SAME dir the webui workspace panel browses,
      so whatever the agent reads/writes shows up there — and nowhere else.
    - ``/memory/`` → ``MemoryBackend`` (DB ``user_configs.agents_md``, the single
      always-loaded AGENTS.md); ``/skills/user/`` + ``/skills/global/`` →
      ``DbSkillsBackend``. Everything but the working files is DB-served.
    - ``/memories/`` → deepagents' ``StoreBackend``: a dynamic, per-user,
      cross-thread memory folder backed by the LangGraph store. The agent uses its
      normal file tools (write_file/read_file/ls/glob/edit_file) to create and
      organize ARBITRARY scenario-specific memory files here on demand — unlike
      ``/memory/AGENTS.md`` (always injected into the prompt), these are read on
      demand. Namespaced ``(uid, "memories")`` so they're private + persist across
      sessions. Store resolved at runtime via ``get_store()`` (the store passed to
      ``create_deep_agent``).
    """
    uid = str(user_id or "default")
    host_root = os.path.join(settings.workspace_root_dir, uid, "workspace")
    os.makedirs(host_root, exist_ok=True)
    working_fs = SessionFilesystemBackend(root_dir=host_root, virtual_mode=True)
    routes: dict[str, object] = {
        "/memory/": MemoryBackend(uid),
        "/memories/": StoreBackend(namespace=lambda _rt, _ns=(uid, "memories"): _ns),
        "/skills/user/": DbSkillsBackend(user_id=uid),
        "/skills/global/": DbSkillsBackend(),  # shipped, read-only — from the DB
    }
    return CompositeBackend(default=working_fs, routes=routes)


async def resolve_model(settings: Settings, requested: str | None, uid: str | None = None) -> str:
    """Return a valid model id for the requested one (or the default), considering
    the user's per-user models merged on top of the global catalog."""
    specs = await merged_model_specs(settings, uid)
    if requested and requested in specs:
        return requested
    return settings.default_model if settings.default_model in specs else next(iter(specs))


# ---------------------------------------------------------------------------
# MCP plugins (global + per-user) → tools
# ---------------------------------------------------------------------------
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


def _split_lines(text: str | None) -> list[str]:
    return [ln.strip() for ln in (text or "").splitlines() if ln.strip()]


def _parse_kv(text: str | None) -> dict:
    """Parse ``KEY=value`` lines (env / headers textareas) into a dict."""
    out: dict[str, str] = {}
    for ln in (text or "").splitlines():
        ln = ln.strip()
        if not ln or "=" not in ln:
            continue
        k, _sep, v = ln.partition("=")
        if k.strip():
            out[k.strip()] = v.strip()
    return out


def _mcp_row_to_cfg(row) -> dict:
    """An MCP table row -> the ``.mcp.json``-shaped cfg dict the connection builder
    and the UI describe path expect (args as a list; env/headers as dicts)."""
    cfg: dict = {"enabled": bool(row.is_active)}
    if row.url:
        cfg["url"] = row.url
        cfg["transport"] = row.transport or "streamable_http"
        if row.headers:
            cfg["headers"] = _parse_kv(row.headers)
    elif row.command:
        cfg["command"] = row.command
        cfg["args"] = _split_lines(row.args)
        if row.env:
            cfg["env"] = _parse_kv(row.env)
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
    conns = _to_connections({
        n: cfg for n, (cfg, _s) in (await _merged_mcp_servers(user_id)).items()
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
            "status": "configured",
            "tool_count": None,
            # Show only command/args/url for display. env/headers are NEVER returned
            # (they may hold ${VAR} secret refs / inline values) — the UI doesn't use them.
            "command": cfg_d.get("command"),
            "args": cfg_d.get("args") or [],
            "url": cfg_d.get("url"),
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


# ---------------------------------------------------------------------------
# CRUD: per-user skills + MCP + models (all DB). Global is READ-ONLY here —
# writes only ever touch the user's own rows.
# ---------------------------------------------------------------------------
def _valid_name(name: str) -> bool:
    return bool(name) and not any(c in name for c in ("/", "\\")) and ".." not in name


def _invalidate_user_cache(user_id: str) -> None:
    """Drop cached agents for a user so skill/MCP/memory edits take effect next call."""
    uid = str(user_id or "default")
    for k in [k for k in _AGENT_CACHE if isinstance(k, tuple) and len(k) >= 2 and k[1] == uid]:
        _AGENT_CACHE.pop(k, None)


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
_MAX_SKILL_FILES = 300
_MAX_FILE_BYTES = 5 * 1024 * 1024
_MAX_SKILL_BYTES = 30 * 1024 * 1024


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
    if raw_len > _MAX_FILE_BYTES:
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
        if zi.file_size > _MAX_FILE_BYTES:
            return {"ok": False, "error": f"{rel} too large"}
        total += zi.file_size
        if total > _MAX_SKILL_BYTES:
            return {"ok": False, "error": "skill too large"}
        if len(collected) >= _MAX_SKILL_FILES:
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


# ---- per-user MCP CRUD (data/users/<uid>/mcp.json; global is read-only) ----
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


def _spec_from_row(settings: Settings, model_id: str, provider_name: str, settings_json: dict) -> dict:
    """Reconstruct a normalized model spec from a DB row, decrypting its secrets.
    Used for BOTH global and user models so build_model_for sees one shape."""
    raw = decrypt_secrets(settings_json or {})
    raw["id"] = model_id
    raw["provider"] = provider_name
    return settings.normalize_model(raw) or {}


async def merged_model_specs(settings: Settings, user_id: str | None = None) -> dict[str, dict]:
    """Global catalog + the user's own models on top, all from the DB (secrets
    decrypted). A user entry with the same id overrides the global one."""
    specs: dict[str, dict] = {}
    async with db_session() as s:
        grows = await s.execute(
            select(GlobalModel, GlobalProvider.name)
            .join(GlobalProvider, GlobalModel.provider_id == GlobalProvider.id)
            .where(GlobalModel.is_active.is_(True))
        )
        for gm, pname in grows.all():
            sp = _spec_from_row(settings, gm.model_id, pname, gm.settings)
            if sp:
                specs[sp["id"]] = sp
        if user_id:
            urows = await s.execute(
                select(UserModel, GlobalProvider.name)
                .join(GlobalProvider, UserModel.provider_id == GlobalProvider.id)
                .where(UserModel.user_id == str(user_id), UserModel.is_active.is_(True))
            )
            for um, pname in urows.all():
                sp = _spec_from_row(settings, um.model_id, pname, um.settings)
                if sp:
                    specs[sp["id"]] = sp
    return specs


async def _is_global_model(mid: str) -> bool:
    async with db_session() as s:
        return (await s.scalar(select(GlobalModel.id).where(GlobalModel.model_id == mid))) is not None


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
        "supports_reasoning": model_supports_reasoning(s),
    }


async def describe_models(settings: Settings, user_id: str) -> list[dict]:
    """Global (read-only) + per-user models for the Providers tab; keys masked."""
    out = []
    async with db_session() as s:
        grows = await s.execute(
            select(GlobalModel, GlobalProvider.name)
            .join(GlobalProvider, GlobalModel.provider_id == GlobalProvider.id)
            .order_by(GlobalModel.model_id)
        )
        for gm, pname in grows.all():
            sp = _spec_from_row(settings, gm.model_id, pname, gm.settings)
            out.append({**_public_model_spec(sp), "scope": "global", "editable": False})
        urows = await s.execute(
            select(UserModel, GlobalProvider.name)
            .join(GlobalProvider, UserModel.provider_id == GlobalProvider.id)
            .where(UserModel.user_id == str(user_id))
            .order_by(UserModel.model_id)
        )
        for um, pname in urows.all():
            sp = _spec_from_row(settings, um.model_id, pname, um.settings)
            out.append({**_public_model_spec(sp), "scope": "user", "editable": True})
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


async def save_user_model(settings, user_id, raw: dict) -> dict:
    """Create/update a per-user model. Secrets left blank/masked keep the old value;
    fresh secrets are Fernet-encrypted at rest (stored in the row's settings JSON)."""
    raw = raw or {}
    mid = str(raw.get("id") or "").strip()
    if not _valid_name(mid):
        return {"ok": False, "error": "invalid model id"}
    if await _is_global_model(mid):
        return {"ok": False, "error": f"'{mid}' is a global (read-only) model"}
    provider = str(raw.get("provider") or "azure_openai").strip().lower()
    if provider not in _VALID_PROVIDERS:
        return {"ok": False, "error": "provider must be azure_openai | anthropic | bedrock | openai | gemini"}
    async with db_session() as s:
        pid = await s.scalar(select(GlobalProvider.id).where(GlobalProvider.name == provider))
        if not pid:
            return {"ok": False, "error": f"unknown provider '{provider}'"}
        row = await s.scalar(
            select(UserModel).where(UserModel.user_id == str(user_id), UserModel.model_id == mid)
        )
        prev_dec = decrypt_secrets(dict(row.settings) if row else {})
        detail: dict = {}
        for k in ("deployment", "endpoint", "api_version", "region", "aws_access_key_id"):
            v = raw.get(k)
            if v not in (None, ""):
                detail[k] = str(v).strip()
        mt = raw.get("max_tokens")
        if mt not in (None, ""):
            try:
                detail["max_tokens"] = int(mt)
            except (TypeError, ValueError):
                pass
        # Secrets: a fresh (non-masked) value is encrypted; blank/masked keeps the prior.
        for sk in _SECRET_FIELDS:
            v = str(raw.get(sk) or "").strip()
            if v and not v.startswith(_MASK):
                detail[sk] = encrypt(v)
            elif prev_dec.get(sk):
                detail[sk] = encrypt(prev_dec[sk])
        err = _validate_model_entry({"provider": provider, **decrypt_secrets(detail)})
        if err:
            return {"ok": False, "error": err}
        if row is None:
            row = UserModel(user_id=str(user_id), model_id=mid)
            s.add(row)
        row.provider_id = pid
        row.settings = detail
        row.is_active = True
    _invalidate_user_cache(user_id)
    return {"ok": True, "id": mid}


async def delete_user_model(settings, user_id, mid) -> dict:
    mid = str(mid or "").strip()
    if await _is_global_model(mid):
        return {"ok": False, "error": f"'{mid}' is a global (read-only) model"}
    async with db_session() as s:
        res = await s.execute(
            sa_delete(UserModel).where(UserModel.user_id == str(user_id), UserModel.model_id == mid)
        )
        existed = (res.rowcount or 0) > 0
    if existed:
        _invalidate_user_cache(user_id)
    return {"ok": existed, "id": mid}


# ---- per-user long-term memory — a single AGENTS.md (user_configs.agents_md) ----
# deepagents' MemoryMiddleware loads this into the prompt; the agent edits it with
# edit_file; the UI Memory panel edits the same column.


async def read_memory(user_id) -> dict:
    """Return {agents_md} text for a user (empty string if unset)."""
    out = {"agents_md": ""}
    try:
        async with db_session() as s:
            cfg = await s.get(UserConfig, str(user_id or ""))
            if cfg:
                out["agents_md"] = getattr(cfg, "agents_md", "") or ""
    except Exception:  # noqa: BLE001
        logger.debug("read_memory failed", exc_info=True)
    return out


async def write_memory(user_id, content) -> dict:
    try:
        async with db_session() as s:
            cfg = await s.get(UserConfig, str(user_id or ""))
            if cfg is None:
                cfg = UserConfig(user_id=str(user_id))
                s.add(cfg)
            cfg.agents_md = content or ""
    except Exception as e:  # noqa: BLE001
        logger.warning("write_memory failed", exc_info=True)
        return {"ok": False, "error": str(e)}
    _invalidate_user_cache(user_id)  # memory feeds the prompt via MemoryMiddleware
    return {"ok": True}


async def _system_prompt_for(user_id) -> str:
    """Just the base prompt — the user's long-term memory (AGENTS.md) is injected
    separately by deepagents' MemoryMiddleware (see ``memory=`` in create_deep_agent)."""
    return DEFAULT_SYSTEM_PROMPT


async def _get_or_build(settings, checkpointer, store, model_id, user_id, *, run_mode, reasoning=None):
    uid = str(user_id or "default")
    mid = await resolve_model(settings, model_id, uid)
    # Reasoning is per-request: bake the (normalized, support-gated) effort into the
    # cache key so a thinking-enabled model is a distinct compiled agent.
    spec = (await merged_model_specs(settings, uid)).get(mid) or {}
    effort = normalize_reasoning_effort(reasoning) if model_supports_reasoning(spec) else None
    key = ("run" if run_mode else "chat", uid, mid, effort)
    agent = _AGENT_CACHE.get(key)
    if agent is not None:
        return agent
    mcp_tools = await load_mcp_tools(settings, uid)
    system_prompt = await _system_prompt_for(uid)
    interrupt_on = None
    if run_mode:
        # Approval policy: gate all MCP/plugin tools, plus any configured built-ins.
        gated = {t.strip() for t in (settings.interrupt_tools or "").split(",") if t.strip()}
        gated |= {getattr(t, "name", None) for t in mcp_tools if getattr(t, "name", None)}
        interrupt_on = {t: True for t in gated if t} or None
    agent = create_deep_agent(
        model=await build_model_for(settings, mid, uid, reasoning=effort),
        tools=mcp_tools,
        system_prompt=system_prompt,
        backend=build_backend(settings, uid),
        checkpointer=checkpointer,
        store=store,
        context_schema=AgentContext,
        interrupt_on=interrupt_on,
        skills=SKILL_SOURCES,
        # deepagents MemoryMiddleware: loads the user's AGENTS.md (served from the
        # DB via the /memory/ mount) into the prompt and lets the agent update it
        # with edit_file. Replaces the old hand-rolled soul/profile/notes injection.
        memory=["/memory/AGENTS.md"],
    )
    _AGENT_CACHE[key] = agent
    logger.info(
        "compiled %s agent user=%s model=%s reasoning=%s mcp_tools=%d gated=%s",
        "run" if run_mode else "chat", uid, mid, effort or "off", len(mcp_tools), list(interrupt_on or {}),
    )
    return agent


async def get_agent(settings, checkpointer, store, model_id=None, user_id="default", reasoning=None):
    """Streaming/chat agent (no approval gating)."""
    return await _get_or_build(settings, checkpointer, store, model_id, user_id, run_mode=False, reasoning=reasoning)


async def get_run_agent(settings, checkpointer, store, model_id=None, user_id="default", reasoning=None):
    """Runs-API agent (MCP/plugin tools gated for HITL approval)."""
    return await _get_or_build(settings, checkpointer, store, model_id, user_id, run_mode=True, reasoning=reasoning)


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


def reasoning_text_from_message(msg) -> str:
    """Extract reasoning / extended-thinking TEXT from a message or streamed chunk.

    Provider formats vary (mirrors hermes-agent's ``extract_reasoning``):
      * Anthropic content blocks ``{"type":"thinking","thinking":...}`` — NOTE: Azure AI
        Foundry returns only a *signature* (no text), confirmed via the raw SDK.
      * OpenAI-compatible: ``reasoning_content`` / ``reasoning`` (DeepSeek-R1, Moonshot, …)
        as a direct attr, in ``additional_kwargs``, or a ``{"type":"reasoning_content"}`` block.
      * OpenRouter unified ``reasoning_details: [{summary|thinking|content|text}]``.
    Returns "" when there's no reasoning text.
    """
    parts: list[str] = []

    def _add(v):
        if isinstance(v, str) and v.strip():
            parts.append(v)

    content = getattr(msg, "content", "")
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            t = block.get("type")
            if t == "thinking":
                _add(block.get("thinking"))
            elif t in ("reasoning_content", "reasoning"):
                _add(block.get("text") or block.get("reasoning") or block.get("thinking"))
    # Direct attributes (DeepSeek/Qwen `reasoning`, Moonshot/Novita `reasoning_content`).
    for attr in ("reasoning", "reasoning_content"):
        _add(getattr(msg, attr, None))
    ak = getattr(msg, "additional_kwargs", None) or {}
    for key in ("reasoning_content", "reasoning"):
        _add(ak.get(key))
    details = ak.get("reasoning_details")
    if isinstance(details, list):
        for d in details:
            if isinstance(d, dict):
                _add(d.get("summary") or d.get("thinking") or d.get("content") or d.get("text"))
    # De-dup (a delta can surface in both content blocks and additional_kwargs).
    seen, out = set(), []
    for p in parts:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return "".join(out)


async def test_model(settings: Settings, user_id: str, model_id: str) -> dict:
    """Live health probe for the Providers-tab status lights. Two tiny real requests:
    ``standard`` (a normal completion works) and ``reasoning`` (the model produces
    reasoning, and whether the reasoning *text* is actually visible in the stream)."""
    out = {
        "id": model_id,
        "standard": {"ok": False},
        "reasoning": {"supported": False, "ok": False, "visible_text": False},
    }
    spec = (await merged_model_specs(settings, user_id)).get(model_id)
    if not spec:
        out["error"] = "unknown model"
        return out
    supported = model_supports_reasoning(spec)
    out["reasoning"]["supported"] = supported
    try:
        m = await build_model_for(settings, model_id, user_id, reasoning=None)
        r = await asyncio.wait_for(m.ainvoke([HumanMessage("Reply with the single word: pong")]), timeout=45)
        out["standard"] = {"ok": True, "sample": _content_to_text(getattr(r, "content", ""))[:60]}
    except Exception as e:  # noqa: BLE001
        out["standard"] = {"ok": False, "error": str(e)[:300]}
    if supported:
        try:
            mr = await build_model_for(settings, model_id, user_id, reasoning="high")
            visible = False

            async def _probe():
                nonlocal visible
                async for ch in mr.astream([HumanMessage("Think briefly step by step, then answer: what is 6 times 7?")]):
                    if reasoning_text_from_message(ch):
                        visible = True

            await asyncio.wait_for(_probe(), timeout=60)
            out["reasoning"] = {"supported": True, "ok": True, "visible_text": visible}
        except Exception as e:  # noqa: BLE001
            out["reasoning"] = {"supported": True, "ok": False, "visible_text": False, "error": str(e)[:300]}
    return out
