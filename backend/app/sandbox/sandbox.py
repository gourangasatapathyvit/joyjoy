"""OpenSandbox lifecycle manager — one sandbox per (user, thread), keyed by the
session's ``workspace_id``.

Durability model (two layers):
  * The DURABLE store is a Docker named volume ``<prefix><workspace_id>`` mounted at
    ``settings.sandbox_mount_path``. It outlives the sandbox (OSEP-0003), so a
    session's files survive sandbox pause/kill/GC and reattach to a fresh sandbox.
  * The sandbox itself is EPHEMERAL execution: a warm in-memory pool keyed by
    workspace_id; idle ones are ``pause()``d. A known ``sandbox_id`` lets us
    ``resume()`` warm, otherwise we ``create()`` a new sandbox attaching the same
    volume (files intact).

CONCURRENCY: the OpenSandbox SDK is async and its aiohttp sessions + this module's
pool/lock must all live on ONE event loop. We run a dedicated background loop and
funnel every SDK/pool touch through it:
  * ``run_sync(coro)`` — for sync callers (the deepagents BaseSandbox file ops run
    in ``asyncio.to_thread`` workers); blocks the worker, never the main loop.
  * ``run_async(coro)`` — for main-loop async callers (the workspace dock).
The public ``*_sync`` / ``*_async`` wrappers below dispatch the internal coroutines
onto the sandbox loop so ``_POOL``/``_LOCK`` are only ever touched there.

Gated by ``settings.sandbox_enabled``; callers check ``is_enabled(settings)`` and
fall back to the host FilesystemBackend when off.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import threading
import time

from opensandbox import Sandbox, SandboxManager
from opensandbox.config import ConnectionConfig
from opensandbox.models.sandboxes import PVC, SandboxFilter, Volume

from app.core.config import Settings
from app.core.textutils import safe_segment

logger = logging.getLogger("joyjoy.sandbox")

# How often the reaper wakes to pause idle sandboxes (seconds).
_REAPER_POLL_S = 60

# --- dedicated sandbox event loop (owns all SDK + pool state) ----------------
_LOOP: asyncio.AbstractEventLoop | None = None
_LOOP_LOCK = threading.Lock()


def _loop() -> asyncio.AbstractEventLoop:
    global _LOOP
    if _LOOP is None:
        with _LOOP_LOCK:
            if _LOOP is None:
                loop = asyncio.new_event_loop()
                threading.Thread(target=loop.run_forever, name="joyjoy-sandbox-loop", daemon=True).start()
                _LOOP = loop
    return _LOOP


def run_sync(coro, timeout: float | None = None):
    """Run ``coro`` on the sandbox loop and block until done (for sync callers)."""
    return asyncio.run_coroutine_threadsafe(coro, _loop()).result(timeout)


async def run_async(coro):
    """Await ``coro`` (which runs on the sandbox loop) from another event loop."""
    return await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(coro, _loop()))


# --- pool state (touched ONLY on the sandbox loop) ---------------------------
_POOL: dict[str, "_Entry"] = {}
_LOCK = asyncio.Lock()
_REAPER: asyncio.Task | None = None


class _Entry:
    __slots__ = ("sandbox", "sandbox_id", "last_used")

    def __init__(self, sandbox, sandbox_id: str):
        self.sandbox = sandbox
        self.sandbox_id = sandbox_id
        self.last_used = time.monotonic()


def is_enabled(settings: Settings) -> bool:
    return bool(settings.sandbox_enabled)


def _conn(settings: Settings):
    return ConnectionConfig(
        domain=settings.sandbox_server_domain,
        protocol=settings.sandbox_server_protocol,
        api_key=settings.opensandbox_api_key or None,
        # In container deployments the backend can't reach per-sandbox endpoints
        # directly; proxy through the server (the only host:port it can reach).
        use_server_proxy=settings.sandbox_use_server_proxy,
    )


def volume_name(settings: Settings, workspace_id: str) -> str:
    return f"{settings.sandbox_volume_prefix}{safe_segment(workspace_id) or 'default'}"


def _volume(settings: Settings, vol: str) -> Volume:
    """Runtime-neutral PERSISTENT per-workspace volume. ``createIfNotExists`` lets the
    OpenSandbox **server** provision the backing store per ITS OWN runtime — a Docker
    named volume OR a Kubernetes PVC — so joyjoy never shells out to ``docker`` and this
    works identically on a single Docker host and on multi-pod Kubernetes.
    We deliberately do NOT set ``deleteOnSandboxTermination`` (it defaults False): the
    volume must OUTLIVE the sandbox (pause/kill/GC) and reattach to the next one — that
    durability is the whole point. Volume deletion is the platform's job (K8s reclaim
    policy / Docker prune)."""
    return Volume(
        name="workspace",
        pvc=PVC(claimName=vol, createIfNotExists=True),
        mountPath=settings.sandbox_mount_path,
    )


async def _create(settings: Settings, workspace_id: str):
    vol = volume_name(settings, workspace_id)
    sb = await Sandbox.create(
        settings.sandbox_image,
        # Durable: server auto-creates the volume; NOT delete-on-terminate, so it
        # survives sandbox pause/kill/GC and reattaches to the next sandbox.
        volumes=[_volume(settings, vol)],
        resource={"cpu": settings.sandbox_cpu, "memory": settings.sandbox_memory},
        timeout=datetime.timedelta(minutes=settings.sandbox_timeout_minutes),
        connection_config=_conn(settings),
    )
    logger.info("created sandbox %s for ws=%s (vol=%s)", sb.id, workspace_id, vol)
    return sb


async def _renew(settings: Settings, sb) -> None:
    try:
        await sb.renew(datetime.timedelta(minutes=settings.sandbox_timeout_minutes))
    except Exception:  # noqa: BLE001
        logger.debug("sandbox renew failed", exc_info=True)


async def _pause_entry(workspace_id: str, entry: "_Entry") -> None:
    try:
        await entry.sandbox.pause()
        logger.info("paused sandbox %s (ws=%s)", entry.sandbox_id, workspace_id)
    except Exception:  # noqa: BLE001
        logger.debug("pause failed for ws=%s", workspace_id, exc_info=True)
    _POOL.pop(workspace_id, None)


async def _enforce_cap(settings: Settings) -> None:
    if len(_POOL) <= settings.sandbox_max_live:
        return
    victims = sorted(_POOL.items(), key=lambda kv: kv[1].last_used)[: len(_POOL) - settings.sandbox_max_live]
    for wid, entry in victims:
        await _pause_entry(wid, entry)


async def _acquire(settings: Settings, workspace_id: str, known_sandbox_id: str | None = None):
    """(runs on the sandbox loop) Return ``(sandbox, sandbox_id)`` for the session,
    creating/resuming as needed."""
    wid = safe_segment(workspace_id) or "default"
    async with _LOCK:
        entry = _POOL.get(wid)
        if entry is not None:
            entry.last_used = time.monotonic()
            await _renew(settings, entry.sandbox)
            return entry.sandbox, entry.sandbox_id

        sb = None
        if known_sandbox_id:
            try:
                sb = await Sandbox.resume(sandbox_id=known_sandbox_id, connection_config=_conn(settings))
                logger.info("resumed sandbox %s for ws=%s", known_sandbox_id, wid)
            except Exception:  # noqa: BLE001
                logger.info("resume %s failed (ws=%s); creating fresh", known_sandbox_id, wid, exc_info=True)
                sb = None
        if sb is None:
            sb = await _create(settings, wid)

        _POOL[wid] = _Entry(sb, sb.id)
        await _enforce_cap(settings)
        return sb, sb.id


async def _kill_session(settings: Settings, workspace_id: str, remove_volume: bool) -> None:
    wid = safe_segment(workspace_id) or "default"
    async with _LOCK:
        entry = _POOL.pop(wid, None)
    if entry is not None:
        try:
            await entry.sandbox.kill()
        except Exception:  # noqa: BLE001
            logger.debug("kill failed for ws=%s", wid, exc_info=True)
    if remove_volume:
        # Durable-volume DELETION is the platform's job, runtime-neutrally — joyjoy does
        # NOT touch it (no host ``docker`` dependency, so this is identical + safe on a
        # single Docker host and on multi-pod Kubernetes):
        #   * Kubernetes — the PVC's reclaim policy / namespace GC removes it.
        #   * Docker     — prune orphaned ``joyjoy-ws-*`` volumes out of band
        #                  (e.g. `docker volume prune`), or via an external reaper.
        # The OpenSandbox SDK can only auto-remove a volume the *terminating* sandbox
        # itself created (``deleteOnSandboxTermination``); that can't apply to a
        # pre-existing durable volume, so there is no in-SDK way to delete it here.
        logger.info(
            "ws=%s deleted; durable volume %s retained for platform reclamation",
            wid, volume_name(settings, wid),
        )


async def _reaper_loop(settings: Settings) -> None:
    idle_s = settings.sandbox_idle_minutes * 60
    while True:
        try:
            await asyncio.sleep(_REAPER_POLL_S)
            now = time.monotonic()
            async with _LOCK:
                stale = [(w, e) for w, e in _POOL.items() if now - e.last_used > idle_s]
                for wid, entry in stale:
                    await _pause_entry(wid, entry)
        except asyncio.CancelledError:
            break
        except Exception:  # noqa: BLE001
            logger.debug("reaper iteration failed", exc_info=True)


async def _shutdown() -> None:
    global _REAPER
    if _REAPER is not None:
        _REAPER.cancel()
        _REAPER = None
    async with _LOCK:
        entries = list(_POOL.items())
        _POOL.clear()
    for wid, entry in entries:
        try:
            await entry.sandbox.pause()
        except Exception:  # noqa: BLE001
            logger.debug("shutdown pause failed for ws=%s", wid, exc_info=True)


async def _healthy(settings: Settings) -> bool:
    try:
        async with await SandboxManager.create(connection_config=_conn(settings)) as mgr:
            await mgr.list_sandbox_infos(SandboxFilter(page_size=1))
        return True
    except Exception:  # noqa: BLE001
        logger.debug("sandbox health probe failed", exc_info=True)
        return False


# --- public API (dispatch onto the sandbox loop) -----------------------------
def acquire_sync(settings: Settings, workspace_id: str, known_sandbox_id: str | None = None):
    """Sync acquire for the deepagents BaseSandbox file ops (called in to_thread)."""
    return run_sync(_acquire(settings, workspace_id, known_sandbox_id))


async def acquire_async(settings: Settings, workspace_id: str, known_sandbox_id: str | None = None):
    """Async acquire for main-loop callers (the workspace dock)."""
    return await run_async(_acquire(settings, workspace_id, known_sandbox_id))


async def kill_session(settings: Settings, workspace_id: str, *, remove_volume: bool = False) -> None:
    await run_async(_kill_session(settings, workspace_id, remove_volume))


async def healthy(settings: Settings) -> bool:
    return await run_async(_healthy(settings))


def start_reaper(settings: Settings) -> None:
    """Start the idle-reaper on the sandbox loop (once, when enabled)."""
    global _REAPER
    if not is_enabled(settings):
        return

    async def _start():
        global _REAPER
        if _REAPER is None:
            _REAPER = asyncio.ensure_future(_reaper_loop(settings))

    run_sync(_start())


async def shutdown() -> None:
    try:
        await run_async(_shutdown())
    except Exception:  # noqa: BLE001
        logger.debug("sandbox shutdown failed", exc_info=True)
