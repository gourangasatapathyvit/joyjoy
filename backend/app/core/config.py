"""Application settings.

Field names are snake_case and map case-insensitively to the UPPER_SNAKE env
vars in ``.env`` (pydantic-settings). A couple of fields use an explicit alias
where the env name differs from the field name.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from urllib.parse import quote

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.enums import Provider


def _read_models_file(path: str) -> list | None:
    """Read the global model catalog file -> list of raw model entries.

    Accepts either ``{"models": [...]}`` or a bare ``[...]``. Returns ``None``
    when the file is absent/unreadable (so callers fall back to the env seed)."""
    try:
        if path and os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            models = data.get("models") if isinstance(data, dict) else data
            return models if isinstance(models, list) else []
    except Exception:
        pass
    return None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Works whether the process is started from joyjoy/ or joyjoy/backend/
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    # ---- Runtime ----
    app_env: str = "dev"
    backend_host: str = "0.0.0.0"
    backend_port: int = 8080
    cors_allowed_origins: str = "*"

    # ---- Gateway auth (hermes-webui -> backend) ----
    gateway_api_key: str = ""
    user_id_header: str = "X-User-Id"
    thread_id_header: str = "X-Thread-Id"
    dev_username: str = "dev-user"  # username for the no-auth dev fallback user (see users.ensure_dev_user)

    # ---- Per-user JWT (direct clients / prod) ----
    jwt_secret: str = ""
    jwt_algorithms: str = "HS256"
    jwt_audience: str = ""

    # ---- Auth (username/password accounts + signed session cookie) ----
    session_cookie: str = "joyjoy_session"
    session_ttl_hours: int = 720  # 30 days
    otp_ttl_minutes: int = 10
    app_public_name: str = "joyjoy"

    # ---- SMTP (password-reset OTP email). When smtp_host is unset the OTP is
    #      logged (dev) instead of emailed. ----
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_starttls: bool = True

    # ---- Postgres (prod) ----
    db_host: str = "localhost"
    db_port: int = 5432
    db_username: str = "postgres"
    db_password: str = ""
    langgraph_db: str = Field(default="langgraph_db", alias="LANGGRAPH_CHECKPOINT_DB")
    database_url: str = ""
    pg_pool_max: int = 20  # max Postgres connections in the prod pool
    interrupt_tools: str = Field(default="", alias="JOYJOY_INTERRUPT_TOOLS")  # extra built-in tools to gate; MCP/plugin tools auto-gate

    # ---- Dev local persistence ----
    sqlite_checkpoint_path: str = "./data/dev_checkpoints.sqlite"
    user_data_root: str = "./data/users"
    # App relational DB (users/skins/providers/skills/mcp/models/sessions/config).
    # Dev → SQLite file; prod → the Postgres in DATABASE_URL (shared w/ LangGraph).
    app_db_path: str = "./data/joyjoy.db"
    # Agent workspace root — the agent's real files live under <workspace_root>/<uid>/
    # workspace/<thread>. session.workspace_path stores the relative key; point this
    # at a shared volume / mount for multi-node. Defaults to user_data_root.
    workspace_root: str = ""
    # DEV-ONLY extra allow-list roots for serving absolute MEDIA: paths outside the
    # workspace (e.g. imported-conversation media on the host). Comma-separated;
    # empty by default. Ignored in prod (workspace is the only allowed root there).
    media_dev_extra_roots: str = ""

    # ---- Skills / MCP ----
    # Global skills + MCP live in the DB, bootstrapped on first boot from the
    # committed SQL seed (app/db/seeds/global_seed.sql). No loose config files.

    # ---- OpenSandbox (per-session agent execution sandbox) ----
    # When enabled, the agent's filesystem + code/shell execution run inside a
    # per-(user,thread) OpenSandbox container backed by a durable Docker named
    # volume (one per workspace_id). Off by default → falls back to the host
    # FilesystemBackend, so the stack works whether or not the sandbox server runs.
    sandbox_enabled: bool = False
    sandbox_server_domain: str = "127.0.0.1:8090"  # host:port of the OpenSandbox server
    sandbox_server_protocol: str = "http"
    opensandbox_api_key: str = Field(default="", alias="OPENSANDBOX_API_KEY")
    # Route ALL sandbox traffic (health-check + file/exec) through the server instead
    # of connecting directly to each sandbox's endpoints. Required when the backend
    # CANNOT reach the per-sandbox container network directly — e.g. docker-compose,
    # where sandboxes are spawned as host-bridge siblings the backend container can't
    # see (direct mode then 30s-timeouts + retries forever). False (direct) is faster
    # and correct only when backend+server+sandboxes share a host (dev/start_all.sh).
    sandbox_use_server_proxy: bool = Field(default=False, alias="SANDBOX_USE_SERVER_PROXY")
    # Fat image (built from backend/../sandbox-image/Dockerfile). v2 = Playwright +
    # browsers + Python data libs (pandas/numpy/matplotlib/openpyxl/python-pptx) AND
    # multi-language runtimes (Node.js 20, JDK 17, Go, Rust, build-essential) + CLI/
    # media/doc tooling (jq/rg/git, ffmpeg/imagemagick, libreoffice/poppler).
    # OpenSandbox runs arbitrary shell, so the image decides language support.
    # Rebuild: docker build -t joyjoy/sandbox-fat:4 sandbox-image/
    sandbox_image: str = "joyjoy/sandbox-fat:4"
    sandbox_cpu: str = "1"
    sandbox_memory: str = "2Gi"
    sandbox_timeout_minutes: int = 30  # sandbox TTL (renewed on use)
    sandbox_idle_minutes: int = 15  # pause a sandbox after this much idle
    sandbox_max_live: int = 16  # cap concurrent live sandboxes (LRU-pause beyond)
    sandbox_volume_prefix: str = "joyjoy-ws-"  # docker volume name = prefix + workspace_id
    sandbox_mount_path: str = "/workspace"  # where the per-session volume mounts

    # ---- Azure OpenAI ----
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_api_version: str = "2024-12-01-preview"
    azure_openai_deployment: str = Field(default="o4-mini", alias="AZURE_OPENAI_DEPLOYMENT_NAME")
    azure_openai_model: str = "o4-mini"
    # JSON array of selectable models (legacy seed; superseded by global_models_path):
    #   [{"id","provider","deployment","endpoint","api_version","api_key"?}, ...]
    models_json: str = Field(default="", alias="JOYJOY_MODELS_JSON")
    # GLOBAL model catalog file (admin/CRUD-managed). Per-user models live under
    # user_data_root/<uid>/models.json. Both are managed from the webui Providers tab.
    global_models_path: str = Field(default="./config/models.json", alias="JOYJOY_GLOBAL_MODELS")

    # ---- Credentials table encryption (prod) ----
    credential_encryption_key: str = ""

    # ---- Observability (metrics + tracing; both optional, off by default) ----
    # Metrics: expose Prometheus metrics at /metrics + instrument runs/HTTP.
    metrics_enabled: bool = False
    # Tracing: route LangChain/LangGraph traces to an OTLP collector (Langfuse) via
    # LangSmith's OTEL bridge. Requires OTEL_EXPORTER_OTLP_ENDPOINT (+ _HEADERS) set;
    # see app/core/observability.setup_tracing. The OTLP env vars are standard.
    tracing_enabled: bool = False
    otel_service_name: str = "joyjoy-backend"

    # ---------- derived ----------
    @property
    def is_prod(self) -> bool:
        return self.app_env.strip().lower() in ("prod", "production")

    @property
    def pg_dsn(self) -> str:
        """psycopg/langgraph connection string for the langgraph database."""
        if self.database_url:
            return self.database_url
        pw = quote(self.db_password, safe="")
        return f"postgresql://{self.db_username}:{pw}@{self.db_host}:{self.db_port}/{self.langgraph_db}"

    @property
    def cors_origins(self) -> list[str]:
        raw = (self.cors_allowed_origins or "").strip()
        if raw in ("", "*"):
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]

    @property
    def app_db_url(self) -> str:
        """Async SQLAlchemy URL for the app DB. Prod → Postgres (psycopg async),
        dev → a local SQLite file."""
        if self.is_prod:
            url = (self.database_url or self.pg_dsn).strip()
            for pre in ("postgresql+psycopg://", "postgresql://", "postgres://"):
                if url.startswith(pre):
                    return "postgresql+psycopg://" + url[len(pre):]
            return url
        path = os.path.abspath(self.app_db_path)
        return f"sqlite+aiosqlite:///{path}"

    @property
    def workspace_root_dir(self) -> str:
        return self.workspace_root or self.user_data_root

    @property
    def media_dev_extra_root_list(self) -> list[str]:
        """Parsed MEDIA_DEV_EXTRA_ROOTS — extra dev-only media allow-list roots.
        ``~`` is expanded; entries are returned as-is for the caller to realpath."""
        return [
            os.path.expanduser(p.strip())
            for p in (self.media_dev_extra_roots or "").split(",")
            if p.strip()
        ]

    def normalize_model(self, m: dict) -> dict | None:
        """Normalize one raw model entry into a full spec.

        Carries a ``provider`` (``azure_openai`` | ``anthropic`` | ``bedrock``)
        so ``build_model_for`` can pick the right LangChain chat model;
        ``anthropic`` covers both api.anthropic.com and Azure AI Foundry's
        ``/anthropic`` Claude endpoint. Azure-only fields fall back to the
        shared ``AZURE_OPENAI_*`` creds; anthropic/bedrock carry their own.
        Extra provider keys (e.g. ``aws_secret_access_key``) pass through.
        All string values get ``${VAR}`` env expansion. Returns ``None`` if no id."""
        if not isinstance(m, dict):
            return None
        mid = str(m.get("id") or "").strip()
        if not mid:
            return None
        provider = Provider.coerce(m.get("provider"))
        is_azure = provider == Provider.AZURE_OPENAI
        spec = dict(m)  # preserve extra provider-specific keys (aws creds, etc.)
        spec.update(
            {
                "id": mid,
                "provider": provider,
                "deployment": m.get("deployment") or mid,
                "endpoint": m.get("endpoint") or (self.azure_openai_endpoint if is_azure else ""),
                "api_version": m.get("api_version") or self.azure_openai_api_version,
                "api_key": m.get("api_key") or (self.azure_openai_api_key if is_azure else ""),
                "region": m.get("region") or "",
                "max_tokens": int(m.get("max_tokens") or 0),
            }
        )
        for k, v in list(spec.items()):
            if isinstance(v, str):
                spec[k] = os.path.expandvars(v)
        return spec

    @property
    def model_specs(self) -> dict[str, dict]:
        """GLOBAL model catalog (one entry per selectable model). Source priority:

          1. ``config/models.json`` (file; CRUD/admin-managed, authoritative)
          2. ``JOYJOY_MODELS_JSON`` env (legacy seed)
          3. the single ``AZURE_OPENAI_*`` model

        Per-user additions are merged on top in ``agent.merged_model_specs()``."""
        entries = _read_models_file(self.global_models_path)
        if entries is None:
            raw = (self.models_json or "").strip()
            if raw:
                try:
                    entries = json.loads(raw)
                except Exception:
                    entries = None
        specs: dict[str, dict] = {}
        for m in entries or []:
            s = self.normalize_model(m)
            if s:
                specs[s["id"]] = s
        if not specs:
            s = self.normalize_model(
                {
                    "id": self.azure_openai_model,
                    "provider": Provider.AZURE_OPENAI,
                    "deployment": self.azure_openai_deployment,
                }
            )
            if s:
                specs[s["id"]] = s
        return specs

    @property
    def default_model(self) -> str:
        specs = self.model_specs
        return self.azure_openai_model if self.azure_openai_model in specs else next(iter(specs))


@lru_cache
def get_settings() -> Settings:
    return Settings()
