from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

_store: Optional[Any] = None


def _get_store():
    """Lazily create and return the AnalysisCacheStore singleton.

    The store's ``pk`` is constructed as ``analysis#<user_pk>`` inside the
    store, so we pass the user_pk from env (HEALTH_PROGRAM_PK) as the
    argument. The store's ``pk`` setter swaps the partition on demand.
    """
    global _store
    if _store is None:
        from analysis_cache import AnalysisCacheStore
        _store = AnalysisCacheStore(
            table_name=os.environ.get(
                "IF_ANALYSIS_CACHE_TABLE_NAME", "if-powerlifting-analysis-cache"
            ),
            pk=os.environ.get("HEALTH_PROGRAM_PK", "operator"),
            region=os.environ.get("AWS_REGION", "ca-central-1"),
        )
        logger.info("[AnalysisCacheGetWindow] AnalysisCacheStore initialised")
    return _store


def _resolve_user_pk(args: dict) -> str:
    return args.get("pk") or os.environ.get("HEALTH_PROGRAM_PK", "operator")


def _store_for(user_pk: str | None):
    """Return the store, retargeted to ``analysis#<user_pk>`` when provided."""
    store = _get_store()
    if user_pk:
        # AnalysisCacheStore prepends "analysis#" to the pk arg.
        store._pk = f"analysis#{user_pk}"
    return store


async def analysis_cache_get_window(args: dict) -> Any:
    """Get the cached per-window analysis bundle.

    Args:
        args: dict with optional `pk`, required `window_key`, optional
              `as_of_date` (informational, unused), and optional `block_key`.
    """
    window_key = args.get("window_key")
    if not window_key:
        raise ValueError("window_key is required")
    block_key = args.get("block_key")
    user_pk = _resolve_user_pk(args)
    store = _store_for(user_pk)
    return store.get_window_analysis(window_key, block_key=block_key)
