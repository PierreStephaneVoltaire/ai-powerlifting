from __future__ import annotations
import logging
import os
from typing import Any, Optional
logger = logging.getLogger(__name__)
_store: Optional[Any] = None

def _get_store():
    global _store
    if _store is None:
        from _federation_store import FederationStore
        _store = FederationStore(
            table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
            pk=os.environ.get("HEALTH_PROGRAM_PK", "operator"),
            region=os.environ.get("AWS_REGION", "ca-central-1"),
        )
        logger.info("[Federation] FederationStore initialised")
    return _store

def _store_for(pk):
    store = _get_store()
    if pk:
        store.pk = pk
    return store

async def federation_user_library_set(args: dict) -> dict:
    pk = args.get("pk") if isinstance(args, dict) else None
    store = _store_for(pk)
    federations = args.get("federations") or []
    standards = args.get("qualification_standards") or []
    return await store.set_user_library(federations, standards)
