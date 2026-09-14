from __future__ import annotations
import logging
import os
from typing import Any, Optional
logger = logging.getLogger(__name__)
_store: Optional[Any] = None

def _get_store():
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
    federations = args.get("federations") if isinstance(args, dict) else None
    standards = args.get("qualification_standards") if isinstance(args, dict) else None
    if not isinstance(federations, list) or not isinstance(standards, list):
        raise ValueError("federations and qualification_standards must be arrays")
    return await store.set_user_library(federations, standards)
