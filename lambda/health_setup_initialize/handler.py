import asyncio
import json

from .core import health_setup_initialize


def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(health_setup_initialize(args))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}