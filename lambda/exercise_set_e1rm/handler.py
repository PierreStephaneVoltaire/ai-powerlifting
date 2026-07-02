import asyncio
import json

from .core import exercise_set_e1rm


def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(exercise_set_e1rm(args))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}