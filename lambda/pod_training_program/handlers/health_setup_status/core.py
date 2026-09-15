from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

_store: Optional["ProgramStore"] = None  # type: ignore[name-defined]


def _get_store():
    """Lazily create and return the ProgramStore singleton."""
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


def _setup_current_program_sk(store) -> str | None:
    from boto3.dynamodb.conditions import Key
    pointer = store.table.get_item(Key={"pk": store.pk, "sk": store.POINTER_SK}, ConsistentRead=True).get("Item")
    if pointer and pointer.get("ref_sk"):
        program = store.table.get_item(Key={"pk": store.pk, "sk": pointer["ref_sk"]}, ConsistentRead=True).get("Item")
        if program and program.get("published", True) is not False:
            return str(pointer["ref_sk"])
    arguments = {"KeyConditionExpression": Key("pk").eq(store.pk) & Key("sk").begins_with(store.PROGRAM_SK_PREFIX), "ConsistentRead": True}
    while True:
        response = store.table.query(**arguments)
        current = next((item for item in response.get("Items", []) if item.get("published", True) is not False), None)
        if current:
            return str(current["sk"])
        if not response.get("LastEvaluatedKey"):
            return None
        arguments["ExclusiveStartKey"] = response["LastEvaluatedKey"]


async def health_setup_status(args: dict | None = None) -> dict:
    """Return first-class setup state for the active health data partition."""
    pk = args.get("pk") if isinstance(args, dict) else None
    store = _store_for(pk)
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