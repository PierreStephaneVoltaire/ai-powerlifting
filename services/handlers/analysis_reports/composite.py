from __future__ import annotations

import base64
import os
from typing import Any

import httpx

from services.dispatch import OperationError


def call_node(operation: str, args: dict[str, Any]) -> Any:
    url = os.environ.get("ANALYTICS_NODE_URL", "http://127.0.0.1:8091").rstrip("/")
    headers = {
        "X-Internal-Token": os.environ.get("ANALYTICS_NODE_TOKEN", os.environ.get("INTERNAL_API_TOKEN", "")),
        "X-Athlete-Pk": str(args.get("pk", "")),
        "X-Person-Pk": str(args.get("_person_pk", args.get("pk", ""))),
        "X-Read-Only": str(bool(args.get("read_only", False))).lower(),
    }
    if args.get("_if_job_id"):
        headers["X-IF-Turn-Id"] = str(args["_if_job_id"])
    payload = {key: value for key, value in args.items() if key not in {"_if_job_id", "_person_pk"}}
    response = httpx.post(f"{url}/internal/analytics/operations/{operation}", headers=headers, json=payload, timeout=900)
    if response.status_code >= 400:
        if response.status_code == 404 and operation in {'analytics.blocks_get', 'analytics.correlation'}:
            detail = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
            raise OperationError(404, 'cache_miss', str(detail.get('error') or 'Analytics report cache miss'))
        raise RuntimeError(response.text or f"Analytics sidecar returned {response.status_code}")
    if response.headers.get("content-type", "").startswith("application/json"):
        value = response.json()
        if isinstance(value, dict) and "data" in value and "error" in value:
            if value["error"]:
                raise RuntimeError(str(value["error"]))
            return value["data"]
        return value
    return {
        "content_base64": base64.b64encode(response.content).decode("ascii"),
        "content_type": response.headers.get("content-type", "application/octet-stream"),
        "content_disposition": response.headers.get("content-disposition", ""),
    }


def handler_for(operation: str):
    def handler(event: dict[str, Any], context: Any) -> Any:
        args = event.get("args", event)
        return call_node(operation, args)

    return handler
