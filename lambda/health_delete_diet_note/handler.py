import asyncio
import json
from .core import health_delete_diet_note
def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(health_delete_diet_note(args["date"]))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}