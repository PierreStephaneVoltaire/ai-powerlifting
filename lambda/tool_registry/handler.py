"""Fission tool_registry handler.

Serves the OpenAPI 3 discovery document for every Fission function under
``utils/powerlifting-app/lambda/`` so that ``health_lambda_mcp`` (and any
other MCP discovery client) can register them on startup.

The document is built lazily from the deploy-time ``LAMBDA_ROOT`` directory:
it walks every sibling tool folder, reads its ``resources.yaml``
``description`` + ``input_schema``, and emits one ``POST /<tool>`` path per
tool (except itself, which is emitted as ``GET /openapi.json``).

Fission routes ``GET /openapi.json`` through the python-env userfunc runtime
without the per-function ``X-Internal-Token`` requirement, so this handler
returns a single static-but-generated-at-startup document instead of the
shared event-based dispatch in ``fission_entry.py``.
"""
from __future__ import annotations

import json
import os
from typing import Any

import yaml


LAMBDA_ROOT = os.environ.get("PL_LAMBDA_ROOT", "/userfunc/deployarchive/lambda")
SELF_TOOL = "tool_registry"


def _load_paths() -> list[str]:
    """Return a sorted list of tool folder names that should appear in the spec."""
    if not os.path.isdir(LAMBDA_ROOT):
        return []
    out: list[str] = []
    for entry in os.listdir(LAMBDA_ROOT):
        if entry == SELF_TOOL or entry.startswith("pl_") or entry == "layers":
            continue
        folder = os.path.join(LAMBDA_ROOT, entry)
        if not os.path.isdir(folder):
            continue
        if not os.path.isfile(os.path.join(folder, "handler.py")):
            continue
        if not os.path.isfile(os.path.join(folder, "resources.yaml")):
            continue
        out.append(entry)
    return sorted(out)


def _tool_entry(tool_id: str) -> dict[str, Any]:
    """Build one path entry for a tool. ``tool_registry`` itself is GET."""
    yaml_path = os.path.join(LAMBDA_ROOT, tool_id, "resources.yaml")
    try:
        with open(yaml_path) as f:
            res = yaml.safe_load(f) or {}
    except Exception:
        res = {}

    description = str(res.get("description") or f"Fission tool: {tool_id}")
    schema = res.get("input_schema") or {"type": "object", "properties": {}, "required": []}
    if not isinstance(schema, dict):
        schema = {"type": "object", "properties": {}, "required": []}
    schema.setdefault("type", "object")
    schema.setdefault("properties", {})

    if tool_id == SELF_TOOL:
        return {
            "get": {
                "operationId": SELF_TOOL,
                "summary": description,
                "description": "Returns the OpenAPI 3 discovery document listing every Fission powerlifting tool.",
                "responses": {
                    "200": {
                        "description": "OpenAPI 3 document",
                        "content": {"application/json": {"schema": {"type": "object"}}},
                    }
                },
            }
        }

    return {
        "post": {
            "operationId": tool_id,
            "summary": description,
            "description": description,
            "requestBody": {
                "required": False,
                "content": {
                    "application/json": {
                        "schema": schema,
                    }
                },
            },
            "responses": {
                "200": {
                    "description": "Tool response",
                    "content": {"application/json": {"schema": {"type": "object"}}},
                },
                "401": {
                    "description": "Missing or invalid X-Internal-Token",
                },
                "500": {
                    "description": "Tool execution error",
                },
            },
        }
    }


def _build_spec() -> dict[str, Any]:
    paths: dict[str, Any] = {}
    for tool_id in _load_paths():
        key = "/openapi.json" if tool_id == SELF_TOOL else f"/{tool_id}"
        paths[key] = _tool_entry(tool_id)
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "Powerlifting Fission Tool Registry",
            "version": "1.0.0",
            "description": (
                "OpenAPI 3 discovery document for the Fission powerlifting tool surface. "
                "Fetched by health_lambda_mcp on startup to register the 94+ tools as MCP tools."
            ),
        },
        "servers": [
            {
                "url": os.environ.get("PL_FISSION_BASE_URL", "http://router.fission.svc.cluster.local:80"),
                "description": "In-cluster Fission router",
            }
        ],
        "paths": paths,
    }


def handler(event, context):  # noqa: ARG001 - Fission signature
    """Fission entry point. ``GET /openapi.json`` returns the discovery doc."""
    try:
        spec = _build_spec()
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(spec, default=str),
        }
    except Exception as exc:  # pragma: no cover - fail-closed response
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": f"tool_registry build failed: {exc}"}),
        }