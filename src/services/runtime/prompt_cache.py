import hashlib
import json
from typing import Any

from services.runtime import valkey

TTL_SECONDS = 30 * 24 * 3600


def cache_request(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: payload.get(key) for key in ("messages", "tools", "response_format")}


def request_hash(request: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(request, sort_keys=True, default=str).encode()).hexdigest()


def _exact_key(athlete: str, operation: str, request: dict[str, Any]) -> str:
    return f"pl:ai-cache:exact:{athlete}:{operation}:{request_hash(request)}"


def exact(athlete: str, operation: str, request: dict[str, Any]) -> dict[str, Any] | None:
    return valkey.get_json(_exact_key(athlete, operation, request))


def remember(athlete: str, operation: str, request: dict[str, Any], response: dict[str, Any]) -> None:
    valkey.set_json(_exact_key(athlete, operation, request), response, ttl=TTL_SECONDS)
