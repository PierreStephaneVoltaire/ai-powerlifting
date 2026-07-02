import asyncio
import json

from .core import health_get_program


def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(health_get_program(args))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}