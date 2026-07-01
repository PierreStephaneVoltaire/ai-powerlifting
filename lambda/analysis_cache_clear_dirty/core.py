from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional

import boto3

logger = logging.getLogger(__name__)

_table = None


def _get_table():
    global _table
    if _table is None:
        region = os.environ.get("AWS_REGION", "ca-central-1")
        table_name = os.environ.get(
            "IF_ANALYSIS_CACHE_TABLE_NAME", "if-powerlifting-analysis-cache"
        )
        _table = boto3.resource("dynamodb", region_name=region).Table(table_name)
        logger.info("[AnalysisCacheClearDirty] DynamoDB table initialised: %s", table_name)
    return _table


def _resolve_user_pk(args: dict) -> str:
    return args.get("pk") or os.environ.get("HEALTH_PROGRAM_PK", "operator")


async def analysis_cache_clear_dirty(args: dict) -> dict:
    """Delete the dirty marker for a user's markdown export.

    Args:
        args: dict with optional `pk` and optional `block_key` (defaults to "current").
              Removes the row with sk = ``markdown_export_dirty#<block_key>``.
    """
    table = _get_table()
    user_pk = _resolve_user_pk(args)
    block_key = args.get("block_key") or "current"
    pk = f"analysis#{user_pk}"
    sk = f"markdown_export_dirty#{block_key}"

    def _sync():
        table.delete_item(Key={"pk": pk, "sk": sk})
        return {"pk": pk, "sk": sk, "block_key": block_key, "deleted": True}

    return await asyncio.get_running_loop().run_in_executor(None, _sync)
