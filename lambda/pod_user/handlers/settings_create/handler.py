import asyncio
import json
from .core import settings_create

def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(settings_create(args))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}
