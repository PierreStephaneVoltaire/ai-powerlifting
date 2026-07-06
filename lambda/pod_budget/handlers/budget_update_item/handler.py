import asyncio
import json

from .core import budget_update_item


def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(budget_update_item(args))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}