from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_federation_store: Optional[Any] = None  # type: ignore[name-defined]


def _get_federation_store():
    global _federation_store
    if _federation_store is None:
        import os
        from federation_store import FederationStore
        _federation_store = FederationStore(
            table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
            pk=os.environ.get("HEALTH_PROGRAM_PK", "operator"),
            region=os.environ.get("AWS_REGION", "ca-central-1"),
        )
    return _federation_store


def _federation_store_for(pk: str | None):
    """Return the FederationStore singleton, retargeted to pk when provided."""
    store = _get_federation_store()
    if pk:
        store.pk = pk
    return store


async def health_get_federation_library(args: dict | None = None) -> dict:
    """Get the shared federation and qualification standards library."""
    pk = args.get("pk") if isinstance(args, dict) else None
    return await _federation_store_for(pk).get_library()