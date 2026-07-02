from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

_store: Optional[Any] = None


def _get_store():
    """Lazily create and return the AnalysisCacheStore singleton."""
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
        logger.info("[AnalysisCacheGetMarkdown] AnalysisCacheStore initialised")
    return _store


def _resolve_user_pk(args: dict) -> str:
    return args.get("pk") or os.environ.get("HEALTH_PROGRAM_PK", "operator")


def _store_for(user_pk: str | None):
    """Return the store, retargeted to ``analysis#<user_pk>`` when provided."""
    store = _get_store()
    if user_pk:
        store._pk = f"analysis#{user_pk}"
    return store


async def analysis_cache_get_markdown(args: dict) -> Any:
    """Get the cached markdown export for the user's current (or past) block.

    Args:
        args: dict with optional `pk` and optional `block_key` (defaults to "current").
    """
    user_pk = _resolve_user_pk(args)
    block_key = args.get("block_key") or "current"
    store = _store_for(user_pk)
    return store.get_markdown_cache(block_key)
