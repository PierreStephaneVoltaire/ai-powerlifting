"""Cancellable executor-process registry for Phase 7.

Maintains an in-process registry of live OpenCode subprocess handles keyed by
run_id. Provides immediate cancel support for same-pod runs via the registry.
Workers poll DynamoDB run record status for cross-pod cancel detection and
set the cancel event when detected.

Only executor/task runs are cancellable; classifier/router runs are never
registered and cannot be cancelled.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from config import OPENCODE_CANCEL_GRACE_SECONDS

logger = logging.getLogger(__name__)


class _RegistryEntry:
    __slots__ = ("process", "cancel_event")

    def __init__(
        self,
        process: asyncio.subprocess.Process,
        cancel_event: asyncio.Event,
    ) -> None:
        self.process = process
        self.cancel_event = cancel_event


_registry: dict[str, _RegistryEntry] = {}


def register(
    run_id: str,
    process: asyncio.subprocess.Process,
    cancel_event: asyncio.Event | None = None,
) -> asyncio.Event:
    if cancel_event is None:
        cancel_event = asyncio.Event()
    _registry[run_id] = _RegistryEntry(process, cancel_event)
    logger.info("Registered cancellable run %s", run_id)
    return cancel_event


def deregister(run_id: str) -> None:
    entry = _registry.pop(run_id, None)
    if entry is not None:
        logger.debug("Deregistered run %s", run_id)


def is_registered(run_id: str) -> bool:
    return run_id in _registry


def request_cancel(run_id: str) -> bool:
    entry = _registry.get(run_id)
    if entry is None:
        logger.debug(
            "Cancel request for unregistered run %s (may be on another pod)",
            run_id,
        )
        return False
    entry.cancel_event.set()
    logger.info("Cancel requested for run %s", run_id)
    return True


async def terminate_and_kill(
    run_id: str,
    grace_seconds: float | None = None,
) -> bool:
    entry = _registry.get(run_id)
    if entry is None:
        return False
    proc = entry.process
    if proc.returncode is not None:
        deregister(run_id)
        return True
    if grace_seconds is None:
        grace_seconds = OPENCODE_CANCEL_GRACE_SECONDS
    try:
        proc.terminate()
    except ProcessLookupError:
        pass
    try:
        await asyncio.wait_for(proc.wait(), timeout=grace_seconds)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        try:
            await proc.wait()
        except Exception:
            pass
    deregister(run_id)
    return True


def get_cancel_event(run_id: str) -> Optional[asyncio.Event]:
    entry = _registry.get(run_id)
    if entry is None:
        return None
    return entry.cancel_event


def clear() -> None:
    _registry.clear()
