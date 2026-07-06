import asyncio
import json

from .core import health_add_exercise


def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(health_add_exercise(args))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}