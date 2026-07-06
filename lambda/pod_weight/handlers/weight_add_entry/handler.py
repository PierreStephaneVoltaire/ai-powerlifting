import asyncio
import json

from .core import weight_add_entry


def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(weight_add_entry(args))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}