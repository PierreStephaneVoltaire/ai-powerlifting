import asyncio
import json
from decimal import Decimal
from .core import health_delete_competition
def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(health_delete_competition(args))
    body = result if isinstance(result, str) else json.dumps(result, default=_json_default)
    return {"statusCode": 200, "body": body}