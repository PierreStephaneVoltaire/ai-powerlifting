import asyncio
import json

from .core import settings_update_ranking_location


def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(settings_update_ranking_location(args))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}