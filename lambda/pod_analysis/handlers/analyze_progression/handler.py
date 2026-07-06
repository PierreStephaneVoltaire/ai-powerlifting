import asyncio
import json

from .core import analyze_progression


def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(analyze_progression(args))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}