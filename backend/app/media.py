"""Media surfacing for the chat stream.

The deepagents agent exposes media two ways:
  1. It WRITES files into the per-session workspace (served by /v1/workspace/raw)
     and the LLM may reference an absolute path with a ``MEDIA:<path>`` line (a
     prompt convention; present in imported hermes conversations).
  2. When it READS a binary file, ``read_file`` returns a ToolMessage whose
     content is LangChain multimodal blocks ``{"type":"image"|"audio"|"video"|
     "file", "base64":..., "mime_type":...}`` (see deepagents
     middleware/filesystem.py) — otherwise flattened away by ``_content_to_text``.

``resolve_media`` safely serves an absolute local file (1); ``media_from_message``
extracts base64 blocks into stream-friendly media descriptors (2).
"""

from __future__ import annotations
import asyncio
import hashlib
import logging
import mimetypes
import os
import re
import shutil
import subprocess
import tempfile

from .constants import DEFAULT_USER_ID, MAX_MEDIA_B64_BYTES, MAX_MEDIA_BYTES, OFFICE_TO_PDF_TIMEOUT_S

logger = logging.getLogger("joyjoy.media")

# Extension groups we serve / preview. Images, A/V and PDF render directly; office
# docs are converted to PDF on demand (office_to_pdf); text/code/markdown files are
# fetched + rendered by the client. Markers the LLM emits can point at any of these.
IMAGE_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico", ".svg", ".heic", ".heif",
}
PDF_EXTS = {".pdf"}
OFFICE_EXTS = {
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".odt", ".ods", ".odp", ".rtf",
}
AV_EXTS = {".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac", ".mp4", ".webm", ".mov", ".m4v"}
TEXT_EXTS = {
    ".md", ".markdown", ".txt", ".csv", ".tsv", ".json", ".jsonl", ".xml",
    ".yaml", ".yml", ".html", ".htm", ".css", ".py", ".js", ".ts", ".tsx",
    ".jsx", ".mjs", ".cjs", ".sh", ".bash", ".zsh", ".go", ".rs", ".java",
    ".kt", ".c", ".cc", ".cpp", ".h", ".hpp", ".rb", ".php", ".sql", ".toml",
    ".ini", ".cfg", ".conf", ".log",
}
ALLOWED_EXTS = IMAGE_EXTS | PDF_EXTS | OFFICE_EXTS | AV_EXTS | TEXT_EXTS

# Byte caps centralized in constants.py (MAX_MEDIA_BYTES / MAX_MEDIA_B64_BYTES).


def is_office(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in OFFICE_EXTS


# Cache of converted PDFs, keyed by (source path, mtime) so re-views are instant.
_PDF_CACHE = os.path.join(tempfile.gettempdir(), "joyjoy_office_pdf")
_SOFFICE = shutil.which("soffice") or shutil.which("libreoffice")


def _convert_office_to_pdf(src: str) -> str | None:
    """Convert an office doc to PDF via headless LibreOffice; cache by mtime.
    Returns the PDF path, or None if soffice is unavailable or conversion fails."""
    if not _SOFFICE or not os.path.isfile(src):
        return None
    try:
        mtime = os.path.getmtime(src)
    except OSError:
        return None
    key = hashlib.sha1(f"{os.path.realpath(src)}:{mtime}".encode()).hexdigest()
    os.makedirs(_PDF_CACHE, exist_ok=True)
    out_pdf = os.path.join(_PDF_CACHE, f"{key}.pdf")
    if os.path.isfile(out_pdf):
        return out_pdf
    # A per-conversion LibreOffice profile dir avoids the "already running" lock
    # when several conversions overlap.
    profile = os.path.join(_PDF_CACHE, f"profile-{key}")
    try:
        subprocess.run(
            [
                _SOFFICE, "--headless", "--norestore",
                f"-env:UserInstallation=file://{profile}",
                "--convert-to", "pdf", "--outdir", _PDF_CACHE, src,
            ],
            capture_output=True, timeout=OFFICE_TO_PDF_TIMEOUT_S, check=False,
        )
    except Exception:  # noqa: BLE001 - treat any failure as "no preview"
        logger.warning("office→pdf conversion failed for %s", src, exc_info=True)
        return None
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    produced = os.path.join(_PDF_CACHE, os.path.splitext(os.path.basename(src))[0] + ".pdf")
    if os.path.isfile(produced):
        if produced != out_pdf:
            try:
                os.replace(produced, out_pdf)
            except OSError:
                return produced
        return out_pdf
    return None


async def office_to_pdf(src: str) -> str | None:
    """Async wrapper — runs the (blocking) LibreOffice conversion off the event loop."""
    return await asyncio.to_thread(_convert_office_to_pdf, src)


def _win_to_wsl(p: str) -> str:
    """Translate a Windows path (``C:\\Users\\…`` — common in imported hermes
    conversations) to its WSL mount (``/mnt/c/Users/…``)."""
    m = re.match(r"^([A-Za-z]):[\\/](.*)$", p)
    if not m:
        return p
    drive, rest = m.group(1).lower(), m.group(2).replace("\\", "/")
    return f"/mnt/{drive}/{rest}"


def _safe_roots(settings, user_id: str) -> list[str]:
    """Dirs an absolute media path is allowed to live under (realpath'd).

    Prod is locked to the per-user workspace only. Extra host roots (configured via
    ``MEDIA_DEV_EXTRA_ROOTS``, e.g. the WSL home or Windows ``/mnt/c/Users``) are
    DEV-only — a convenience for testing imported-conversation media that references
    absolute host paths. In prod they'd let a crafted ``MEDIA:`` marker surface
    arbitrary host/home files to the chat client, so they're ignored there.
    """
    # Use the SAME root as the workspace dock/agent (WORKSPACE_ROOT, falling back to
    # user_data_root) so host-mode MEDIA: markers resolve where files actually live.
    ws = os.path.join(settings.workspace_root_dir, str(user_id or DEFAULT_USER_ID), "workspace")
    cands = [ws]
    if not settings.is_prod:
        cands += settings.media_dev_extra_root_list
    roots: list[str] = []
    for cand in cands:
        try:
            rp = os.path.realpath(cand)
            if os.path.isdir(rp):
                roots.append(rp)
        except OSError:
            continue
    return roots


def resolve_media(settings, user_id: str, raw_path: str) -> tuple[str, str] | None:
    """(absolute path, mime) for a serveable local media file, or None if missing,
    too large, the wrong type, or outside the allowed roots."""
    if not raw_path:
        return None
    cleaned = _win_to_wsl(raw_path.strip().strip("\"'`"))
    full = os.path.realpath(os.path.expanduser(cleaned))
    if os.path.splitext(full)[1].lower() not in ALLOWED_EXTS:
        return None
    roots = _safe_roots(settings, user_id)
    if not any(full == r or full.startswith(r + os.sep) for r in roots):
        return None
    if not os.path.isfile(full):
        return None
    try:
        if os.path.getsize(full) > MAX_MEDIA_BYTES:
            return None
    except OSError:
        return None
    mime = mimetypes.guess_type(full)[0] or "application/octet-stream"
    return full, mime


def media_from_message(m) -> list[dict]:
    """Extract base64 media blocks from a (Tool)Message into stream descriptors:
    ``{kind, mime_type, filename?, data_url}``. Empty for plain-text messages."""
    blocks = None
    content = getattr(m, "content", None)
    if isinstance(content, list):
        blocks = content
    else:
        cb = getattr(m, "content_blocks", None)
        if isinstance(cb, list):
            blocks = cb
    if not blocks:
        return []

    ak = getattr(m, "additional_kwargs", None) or {}
    src = ak.get("read_file_path")
    filename = os.path.basename(src) if isinstance(src, str) and src else None

    out: list[dict] = []
    for b in blocks:
        if not isinstance(b, dict):
            continue
        kind = b.get("type")
        if kind not in ("image", "audio", "video", "file"):
            continue
        b64 = b.get("base64") or b.get("data")
        if not isinstance(b64, str) or not b64 or len(b64) > MAX_MEDIA_B64_BYTES:
            continue
        mime = b.get("mime_type") or b.get("mimeType") or "application/octet-stream"
        out.append(
            {
                "kind": kind,
                "mime_type": mime,
                "filename": filename,
                "data_url": f"data:{mime};base64,{b64}",
            }
        )
    return out
