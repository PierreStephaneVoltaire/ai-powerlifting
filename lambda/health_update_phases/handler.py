import asyncio
import json
from .core import health_update_phases
def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(health_update_phases(args["phases"]))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}