import asyncio
import json
from .core import federation_master_update

def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(federation_master_update(args))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}
