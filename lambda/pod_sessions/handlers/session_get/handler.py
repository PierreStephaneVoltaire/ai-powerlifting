import asyncio
import json

from .core import session_get


def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(session_get(args))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}
