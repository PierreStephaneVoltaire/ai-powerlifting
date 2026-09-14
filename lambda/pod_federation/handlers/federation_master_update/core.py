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

async def federation_master_update(args: dict) -> dict:
    pk = args.get("pk") if isinstance(args, dict) else None
    store = _store_for(pk)
    master_id = args.get("master_id") if isinstance(args, dict) else None
    updates = args.get("updates") if isinstance(args, dict) else None
    if not isinstance(master_id, str) or not master_id.strip():
        raise ValueError("master_id is required")
    if not isinstance(updates, dict) or not updates:
        raise ValueError("updates must be a non-empty object")
    allowed = {
        "name", "abbreviation", "region", "website_url", "status",
        "source_slug", "has_standards", "standard_unit", "standards",
        "display_options", "parent_federation_abbr", "membership_group",
    }
    unknown = set(updates) - allowed
    if unknown:
        raise ValueError(f"unsupported federation fields: {sorted(unknown)}")
    await store.update_master_federation(master_id, updates)
    return {"success": True}
