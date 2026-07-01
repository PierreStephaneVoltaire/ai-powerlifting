import asyncio
import json

from .core import profile_get_current


def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(profile_get_current(args))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}