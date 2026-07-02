import asyncio
import json

from .core import health_snapshot_competition_projection


def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(health_snapshot_competition_projection(args))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}