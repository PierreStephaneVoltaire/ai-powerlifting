import asyncio
import json

from .core import regenerate_analysis


def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(regenerate_analysis(args))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}