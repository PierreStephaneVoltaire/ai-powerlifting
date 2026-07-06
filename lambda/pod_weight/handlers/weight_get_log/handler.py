import asyncio
import json

from .core import weight_get_log


def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(weight_get_log(args))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}