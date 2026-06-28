import json
import os


def _load_registry():
    registry_path = os.path.join(os.path.dirname(__file__), "resources.json")
    with open(registry_path) as f:
        return json.load(f)


def _build_openapi(registry):
    paths = {}
    for tool_name in sorted(registry):
        entry = registry[tool_name]
        description = entry.get("description", "") or ""
        input_schema = entry.get("input_schema", {}) or {}
        paths["/" + tool_name] = {
            "post": {
                "summary": description,
                "operationId": tool_name,
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": input_schema
                        }
                    }
                },
                "responses": {
                    "200": {
                        "description": "Tool result"
                    }
                },
            }
        }
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "Powerlifting Health Lambdas",
            "version": "1",
        },
        "paths": paths,
    }


def handler(event, context):
    registry = _load_registry()
    openapi = _build_openapi(registry)
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(openapi),
    }