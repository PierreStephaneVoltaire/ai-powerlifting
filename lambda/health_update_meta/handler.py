import asyncio
import json
from .core import health_update_meta
def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(health_update_meta(args))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}