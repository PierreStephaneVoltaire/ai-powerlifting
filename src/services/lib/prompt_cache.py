import hashlib
import json
import logging
import os
import re
import uuid
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from services.lib import valkey

logger = logging.getLogger(__name__)

SEARCH_TOOL = "external__prompt_cache__qdrant-find"


def collection(athlete: str, operation: str) -> str:
    return "pc_" + re.sub(r"[^A-Za-z0-9_-]", "_", f"{athlete}__{operation}")


def cache_request(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: payload.get(key) for key in ("messages", "tools", "response_format")}


def request_hash(request: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(request, sort_keys=True, default=str).encode()).hexdigest()


def searchable_text(request: dict[str, Any]) -> str:
    return "\n\n".join(
        message["content"] if isinstance(message.get("content"), str) else json.dumps(message.get("content"), default=str)
        for message in request.get("messages") or []
        if message.get("role") != "system"
    )


def _entry_key(entry_id: str) -> str:
    return f"pl:prompt-cache:entry:{entry_id}"


def _exact_key(athlete: str, operation: str, request: dict[str, Any]) -> str:
    return f"pl:prompt-cache:exact:{athlete}:{operation}:{request_hash(request)}"


def entry(athlete: str, operation: str, entry_id: str) -> dict[str, Any] | None:
    record = valkey.get_json(_entry_key(entry_id))
    if not record or record["athlete"] != athlete or record["operation"] != operation:
        return None
    return record["response"]


def exact(athlete: str, operation: str, request: dict[str, Any]) -> dict[str, Any] | None:
    entry_id = valkey.get_json(_exact_key(athlete, operation, request))
    return entry(athlete, operation, entry_id) if entry_id else None


def has_entries(athlete: str, operation: str) -> bool:
    try:
        response = httpx.get(f"{os.environ.get('PROMPT_CACHE_QDRANT_URL', 'http://pl-prompt-cache:6333')}/collections/{collection(athlete, operation)}", timeout=3)
    except httpx.HTTPError as exc:
        logger.warning("Prompt cache collection check failed: %s", exc)
        return False
    return response.status_code == 200 and response.json()["result"]["points_count"] > 0


async def remember(athlete: str, operation: str, request: dict[str, Any], response: dict[str, Any]) -> None:
    entry_id = uuid.uuid4().hex
    valkey.set_json(_entry_key(entry_id), {"athlete": athlete, "operation": operation, "response": response})
    valkey.set_json(_exact_key(athlete, operation, request), entry_id)
    try:
        async with streamable_http_client(os.environ.get("PROMPT_CACHE_MCP_URL", "http://pl-prompt-cache-mcp:8000/mcp")) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await session.call_tool("qdrant-store", {
                    "information": searchable_text(request),
                    "collection_name": collection(athlete, operation),
                    "metadata": {"entry_id": entry_id},
                })
    except Exception as exc:
        logger.warning("Prompt cache store failed: %s", exc)
