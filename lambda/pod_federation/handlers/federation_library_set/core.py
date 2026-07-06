from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

_store: Optional[Any] = None


def _get_store():
    """Lazily create and return the FederationLibraryStore singleton."""
    global _store
    if _store is None:
        from federation_library_store import FederationLibraryStore
        _store = FederationLibraryStore(
            table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
            pk=os.environ.get("HEALTH_PROGRAM_PK", "operator"),
            region=os.environ.get("AWS_REGION", "ca-central-1"),
        )
        logger.info("[FederationLibrarySet] FederationLibraryStore initialised")
    return _store


def _store_for(pk: str | None):
    """Return the store, retargeted to pk when provided."""
    store = _get_store()
    if pk:
        store.pk = pk
    return store


async def federation_library_set(args: dict) -> dict:
    """Replace the per-user federation library entries.

    Args:
        args: dict with optional `pk` and required `entries` (list).
    """
    pk = args.get("pk") if isinstance(args, dict) else None
    entries = args.get("entries") if isinstance(args, dict) else None
    if not isinstance(entries, list):
        raise ValueError("entries must be a list of federation library entries")
    store = _store_for(pk)
    return await store.set_library(entries)
