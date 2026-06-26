"""Relational schema (SQLAlchemy 2.0). Dev → SQLite, prod → Postgres (same
tables). Chat messages stay in LangGraph's checkpointer; everything else
(accounts, config, skills, MCP, models, sessions) lives here.

Conventions: surrogate string-UUID PKs (so a username/email rename never breaks
FKs); unique natural keys where they matter; JSON columns for free-form blobs
(provider field-schemas, model settings, skin accent vars, sidebar order); secret
fields inside `settings` JSON are Fernet-encrypted at rest (see db/crypto.py).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.timeutils import utcnow


def _uuid() -> str:
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    pass


# ── Accounts ─────────────────────────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"
    # id is the tenant identity threaded everywhere (session-cookie `sub`); a
    # surrogate uuid so username/email can change without breaking per-user FKs.
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    # display_name lives in UserConfig (it's surfaced via /v1/settings/ui, not /auth/me)


class PasswordReset(Base):
    __tablename__ = "password_resets"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    otp_hash: Mapped[str] = mapped_column(String(255))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ── Global catalogs (read-only shipped defaults; seeded on startup) ──────────
class Skin(Base):
    __tablename__ = "skins"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(64), unique=True)  # gold/ares/poseidon/...
    label: Mapped[str] = mapped_column(String(64), default="")
    config: Mapped[dict] = mapped_column(JSON, default=dict)  # {color, ...accent vars}
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class GlobalProvider(Base):
    __tablename__ = "global_providers"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(64), unique=True)  # azure_openai/anthropic/...
    label: Mapped[str] = mapped_column(String(128), default="")
    config_schema: Mapped[dict] = mapped_column(JSON, default=dict)  # the Add-model form fields
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class GlobalModel(Base):
    __tablename__ = "global_models"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    model_id: Mapped[str] = mapped_column(String(128), unique=True)  # gpt-5, o3, ...
    provider_id: Mapped[str] = mapped_column(ForeignKey("global_providers.id"), index=True)
    settings: Mapped[dict] = mapped_column(JSON, default=dict)  # deployment/endpoint/... (+enc secrets)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class GlobalSkill(Base):
    __tablename__ = "global_skills"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[str] = mapped_column(Text, default="")  # SKILL.md
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class GlobalMcp(Base):
    __tablename__ = "global_mcps"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    transport: Mapped[str] = mapped_column(String(16), default="stdio")  # stdio|http
    command: Mapped[str] = mapped_column(Text, default="")
    args: Mapped[str] = mapped_column(Text, default="")  # one per line
    env: Mapped[str] = mapped_column(Text, default="")  # KEY=value per line
    url: Mapped[str] = mapped_column(Text, default="")
    headers: Mapped[str] = mapped_column(Text, default="")  # KEY=value per line
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


# ── Per-user data ───────────────────────────────────────────────────────────
class UserConfig(Base):
    __tablename__ = "user_configs"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(128), default="")  # Profile "display name"
    skin_id: Mapped[str | None] = mapped_column(ForeignKey("skins.id"), nullable=True)
    theme: Mapped[str] = mapped_column(String(16), default="dark")  # dark | light | system (joyjoy brand = dark)
    auto_follow: Mapped[bool] = mapped_column(Boolean, default=True)
    activity_display: Mapped[str] = mapped_column(String(16), default="compact")
    sidebar_order: Mapped[list] = mapped_column(JSON, default=list)
    default_model: Mapped[str] = mapped_column(String(128), default="")
    default_reasoning: Mapped[str] = mapped_column(String(16), default="off")
    # Account default for new chats' auto-approve (per-chat override lives on Session).
    auto_approve_default: Mapped[bool] = mapped_column(Boolean, default=False)
    locale: Mapped[str] = mapped_column(String(16), default="en")
    # Single per-user long-term memory doc (deepagents AGENTS.md convention),
    # loaded by MemoryMiddleware and editable by the agent (edit_file) + the UI.
    agents_md: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class UserModel(Base):
    __tablename__ = "user_models"
    __table_args__ = (UniqueConstraint("user_id", "model_id", name="uq_user_model"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider_id: Mapped[str] = mapped_column(ForeignKey("global_providers.id"))
    model_id: Mapped[str] = mapped_column(String(128))
    settings: Mapped[dict] = mapped_column(JSON, default=dict)  # endpoint/deployment/... (+enc secrets)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class UserSkill(Base):
    __tablename__ = "user_skills"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_user_skill"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[str] = mapped_column(Text, default="")  # SKILL.md
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class UserMcp(Base):
    __tablename__ = "user_mcps"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_user_mcp"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    transport: Mapped[str] = mapped_column(String(16), default="stdio")
    command: Mapped[str] = mapped_column(Text, default="")
    args: Mapped[str] = mapped_column(Text, default="")
    env: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str] = mapped_column(Text, default="")
    headers: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class SkillFile(Base):
    __tablename__ = "skill_files"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    global_skill_id: Mapped[str | None] = mapped_column(
        ForeignKey("global_skills.id", ondelete="CASCADE"), nullable=True, index=True
    )
    user_skill_id: Mapped[str | None] = mapped_column(
        ForeignKey("user_skills.id", ondelete="CASCADE"), nullable=True, index=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text, default="")
    encoding: Mapped[str] = mapped_column(String(16), default="utf-8")  # utf-8 | base64 (binary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Session(Base):
    __tablename__ = "sessions"
    thread_id: Mapped[str] = mapped_column(String(64), primary_key=True)  # the LangGraph thread id
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255), default="New chat")
    default_model: Mapped[str] = mapped_column(String(128), default="")
    reasoning: Mapped[str] = mapped_column(String(16), default="off")
    # Per-thread HITL policy: when true, gated tool calls in this conversation are
    # approved automatically (no approval card). Seeded from the user's account
    # default on creation; overridable per chat. See runs._drive enforcement.
    auto_approve: Mapped[bool] = mapped_column(Boolean, default=False)
    # Pinned conversations sort to the top of the per-user sidebar (user-scoped via
    # the row's user_id). See sessions.list_sessions ordering + update_session.
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    workspace_path: Mapped[str] = mapped_column(String(255), default="")  # relative to workspace_root
    forked_from: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Per-thread UI telemetry persisted from the last run so the Context Display
    # badge + Sources footer survive reloads: {"usage": {...}, "sources": [...]}.
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
