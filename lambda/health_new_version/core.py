from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_store: Optional["ProgramStore"] = None  # type: ignore[name-defined]


def _get_store():
    """Lazily create and return the ProgramStore singleton."""
    global _store
    if _store is None:
        import os
        from program_store import ProgramStore as _PS
        _store = _PS(
            table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
            pk=os.environ.get("HEALTH_PROGRAM_PK", "operator"),
            region=os.environ.get("AWS_REGION", "ca-central-1"),
        )
        logger.info("[HealthTools] ProgramStore initialised from env vars")
    return _store


def _store_for(pk: str | None):
    """Return the ProgramStore singleton, retargeted to pk when provided."""
    store = _get_store()
    if pk:
        store.pk = pk
    return store


async def health_new_version(args: dict | None = None, change_reason: str | None = None, patches: list[dict] | None = None) -> dict:
    """Create a new major version of the program.

    Args:
        change_reason: Human-readable reason for the version change
        patches: List of patches, each with "path" and "value" keys
                Example: {"path": "sessions[0].exercises[1].kg", "value": 180}

    Returns:
        {"new_version": int, "change_reason": str}

    Raises:
        ValueError: If patch format invalid
        RuntimeError: If store not initialized or DynamoDB fails
    """
    if isinstance(args, dict):
        if change_reason is None:
            change_reason = args.get("change_reason")
        if patches is None:
            patches = args.get("patches")
    pk = args.get("pk") if isinstance(args, dict) else None
    store = _store_for(pk)
    updated_program = await store.new_version(patches, change_reason)

    version_label = updated_program.get("meta", {}).get("version_label", "unknown")

    return {
        "new_version": version_label,
        "change_reason": change_reason,
    }