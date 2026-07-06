import asyncio
import json

from .core import max_target_update


def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(max_target_update(args))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}
