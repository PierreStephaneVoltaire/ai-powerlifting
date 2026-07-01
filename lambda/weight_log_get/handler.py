import asyncio
import json

from .core import weight_log_get


def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(weight_log_get(args))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}
