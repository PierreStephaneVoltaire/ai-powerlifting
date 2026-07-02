import asyncio
import json

from .core import master_copy_seed_user


def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(master_copy_seed_user(args))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}
