import asyncio
import json

from .core import video_remove


def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(video_remove(args))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}