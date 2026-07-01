import asyncio
import json

from .core import exercise_unarchive


def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(exercise_unarchive(args))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}