import asyncio
import json

from .core import budget_put_config


def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(budget_put_config(args))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}