import asyncio
import json

from .core import days_until


def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(days_until(args["target_date"], args.get("label", "target")))
    if isinstance(result, str):
        body = result
    else:
        body = json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}