"""Shared helpers for the session_* fission tools.

Each session tool is a thin async wrapper over `SessionStore`. These helpers
build the singleton store (retargeted to the caller's pk) and resolve the
current program SK + phases, so individual tool core.py files stay tiny and the
backend session controller becomes a pure auth/pk router.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

_store: Optional[Any] = None


def get_store(args: Optional[dict] = None):
    """Lazily create / retarget the SessionStore singleton."""
    global _store
    if _store is None:
        from session_store import SessionStore as _SS
        _store = _SS(
            table_name=os.environ.get("IF_SESSIONS_TABLE_NAME", "if-sessions"),
            pk=os.environ.get("HEALTH_PROGRAM_PK", "operator"),
            region=os.environ.get("AWS_REGION", "ca-central-1"),
            source_table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
        )
        logger.info("[SessionTools] SessionStore initialised from env vars")
    pk = (args or {}).get("pk")
    if pk:
        _store._pk = pk
    return _store


async def resolve_context(store, program_sk: Optional[str] = None):
    """Return (program_sk, phases). If program_sk is not supplied, resolve the
    current program SK from the program#current pointer (frontend always
    operates on current — no version handling)."""
    if not program_sk:
        program_sk = await store.resolve_program_sk()
    phases = await store.load_phases(program_sk)
    return program_sk, phases
