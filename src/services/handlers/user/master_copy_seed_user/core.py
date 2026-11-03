from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

_service: Optional[Any] = None


def _get_service():
    """Lazily create and return the MasterCopyService singleton."""
    global _service
    if _service is None:
        from master_copy import MasterCopyService
        _service = MasterCopyService(
            table_prefix="",
            region=os.environ.get("AWS_REGION", "ca-central-1"),
        )
        logger.info("[MasterCopySeedUser] MasterCopyService initialised")
    return _service


def _resolve_pk(args: dict) -> str:
    return args.get("pk") or os.environ.get("HEALTH_PROGRAM_PK", "operator")


async def master_copy_seed_user(args: dict) -> dict:
    """Seed per-user copies of master competitions and federations.

    Args:
        args: dict with optional `pk` (defaults to env HEALTH_PROGRAM_PK).
    """
    service = _get_service()
    pk = _resolve_pk(args)
    return await service.seed_user_from_master(pk)
