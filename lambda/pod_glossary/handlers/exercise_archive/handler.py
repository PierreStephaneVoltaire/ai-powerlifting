import asyncio
import json

from .core import exercise_archive


def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(exercise_archive(args))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}