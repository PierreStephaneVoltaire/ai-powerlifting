import hashlib
import json
import logging
import os
from datetime import date
from typing import Any

import httpx

from services.runtime import analysis_version

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 20


def _url() -> str:
    return os.environ.get("PROMPT_CACHE_URL", "http://pl-prompt-cache-api.powerlifting.svc.cluster.local:8000").rstrip("/")


def cache_request(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: payload.get(key) for key in ("messages", "tools", "response_format")}


def request_hash(request: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(request, sort_keys=True, default=str).encode()).hexdigest()


def request_context(athlete: str) -> dict[str, str]:
    return {"date": date.today().isoformat(), "analysis_version": analysis_version.current(athlete)}


def _post(path: str, body: dict[str, Any]) -> dict[str, Any] | None:
    try:
        response = httpx.post(f"{_url()}{path}", content=json.dumps(body, default=str), headers={"Content-Type": "application/json"}, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Prompt cache %s failed: %s", path, exc)
        return None


def lookup(athlete: str, operation: str, request: dict[str, Any], context: dict[str, str]) -> tuple[dict[str, Any], str] | None:
    result = _post("/lookup", {"athlete": athlete, "operation": operation, "request": request, "context": context})
    if not result or not result.get("hit") or result.get("response") is None:
        return None
    return result["response"], result.get("layer") or "exact"


def remember(athlete: str, operation: str, request: dict[str, Any], response: dict[str, Any], context: dict[str, str]) -> None:
    _post("/store", {"athlete": athlete, "operation": operation, "request": request, "response": response, "context": context})
