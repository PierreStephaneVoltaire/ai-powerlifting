import asyncio
import json

from .core import health_get_sessions_range


def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(health_get_sessions_range(args["start_date"], args["end_date"]))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}