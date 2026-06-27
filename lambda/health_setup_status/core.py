from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

_store: Optional["ProgramStore"] = None  # type: ignore[name-defined]


def _get_store():
    """Lazily create and return the ProgramStore singleton."""
    global _store
    if _store is None:
        from program_store import ProgramStore as _PS
        _store = _PS(
            table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
            pk=os.environ.get("HEALTH_PROGRAM_PK", "operator"),
            region=os.environ.get("AWS_REGION", "ca-central-1"),
        )
        logger.info("[HealthTools] ProgramStore initialised from env vars")
    return _store


def _setup_current_program_sk(store) -> str | None:
    pointer = store.table.get_item(Key={"pk": store.pk, "sk": store.POINTER_SK}).get("Item")
    if pointer:
        ref_sk = pointer.get("ref_sk") or "program#v001"
        program = store.table.get_item(Key={"pk": store.pk, "sk": str(ref_sk)}).get("Item")
        return str(ref_sk) if program else None

    try:
        from boto3.dynamodb.conditions import Key
        result = store.table.query(
            KeyConditionExpression=Key("pk").eq(store.pk) & Key("sk").begins_with(store.PROGRAM_SK_PREFIX),
            Limit=1,
        )
        items = result.get("Items", [])
        return str(items[0]["sk"]) if items else None
    except Exception:
        program = store.table.get_item(Key={"pk": store.pk, "sk": "program#v001"}).get("Item")
        return "program#v001" if program else None


async def health_setup_status() -> dict:
    """Return first-class setup state for the active health data partition."""
    store = _get_store()
    current_sk = await asyncio.get_running_loop().run_in_executor(
        None,
        lambda: _setup_current_program_sk(store),
    )
    has_current = bool(current_sk)
    return {
        "mapped_pk": store.pk,
        "hasCurrentProgram": has_current,
        "needsSetup": not has_current,
        "currentProgramSk": current_sk,
    }