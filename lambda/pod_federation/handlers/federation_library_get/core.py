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
        from _federation_library_store import FederationLibraryStore
        _store = FederationLibraryStore(
            table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
            pk=os.environ.get("HEALTH_PROGRAM_PK", "operator"),
            region=os.environ.get("AWS_REGION", "ca-central-1"),
        )
        logger.info("[FederationLibraryGet] FederationLibraryStore initialised")
    return _store


def _store_for(pk: str | None):
    """Return the store, retargeted to pk when provided."""
    store = _get_store()
    if pk:
        store.pk = pk
    return store


async def federation_library_get(args: dict) -> dict:
    """Get the per-user federation library.

    Args:
        args: dict with optional `pk`.
    """
    pk = args.get("pk") if isinstance(args, dict) else None
    store = _store_for(pk)
    return await store.get_library()
