import asyncio
import json

from .core import health_list_competitions


def handler(event, context):
    args = event.get("args", event) or {}
    result = asyncio.run(health_list_competitions(args))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}
