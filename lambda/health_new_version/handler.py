import asyncio
import json

from .core import health_new_version


def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(health_new_version(args["change_reason"], args["patches"]))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}