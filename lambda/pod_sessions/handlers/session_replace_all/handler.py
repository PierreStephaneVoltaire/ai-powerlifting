import asyncio
import json

from .core import session_replace_all


def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(session_replace_all(args))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}
