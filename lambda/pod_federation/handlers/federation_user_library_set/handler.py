import asyncio
import json
from .core import federation_user_library_set

def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(federation_user_library_set(args))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}
