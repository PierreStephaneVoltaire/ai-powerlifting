from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

_store: Optional[Any] = None


def _get_store():
    """Lazily create and return the FederationStore singleton.

    The FederationStore reads the GLOBAL federation library from
    sk = ``federations#v1``. This is distinct from the per-user
    ``federation_library#v1`` item (owned by FederationLibraryStore).
    """
    global _store
    if _store is None:
        from federation_store import FederationStore
        _store = FederationStore(
            table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
            pk=os.environ.get("HEALTH_PROGRAM_PK", "operator"),
            region=os.environ.get("AWS_REGION", "ca-central-1"),
        )
        logger.info("[FederationList] FederationStore initialised")
    return _store


def _store_for(pk: str | None):
    store = _get_store()
    if pk:
        store.pk = pk
    return store


async def federation_list(args: dict) -> dict:
    """Return the global federation library for a user.

    Args:
        args: dict with optional `pk`.
    """
    pk = args.get("pk") if isinstance(args, dict) else None
    store = _store_for(pk)
    library = await store.get_library()
    entries = library.get("federations", []) or []
    return {
        "entries": entries,
        "qualification_standards": library.get("qualification_standards", []) or [],
        "updated_at": library.get("updated_at", ""),
        "count": len(entries) if isinstance(entries, list) else 0,
    }
