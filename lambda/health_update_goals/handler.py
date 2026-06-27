import asyncio
import json
from .core import health_update_goals
def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(health_update_goals(args["goals"]))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}