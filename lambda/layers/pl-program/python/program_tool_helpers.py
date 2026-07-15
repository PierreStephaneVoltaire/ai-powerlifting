"""Shared helpers for the program_* fission tools."""
from __future__ import annotations
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)
_store: Optional[Any] = None

def get_store(args: Optional[dict] = None):
    global _store
    if _store is None:
        from program_store import ProgramStore as _PS
        _store = _PS(
            table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
            pk=os.environ.get("HEALTH_PROGRAM_PK", "operator"),
            region=os.environ.get("AWS_REGION", "ca-central-1"),
        )
        logger.info("[ProgramTools] ProgramStore initialised from env vars")
    pk = (args or {}).get("pk")
    if pk:
        _store.pk = pk
    return _store
