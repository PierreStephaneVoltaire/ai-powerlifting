import asyncio
import json

from .core import goals_list


def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(goals_list(args))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}
