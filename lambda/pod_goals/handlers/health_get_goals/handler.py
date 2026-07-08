import asyncio
import json
from decimal import Decimal
from .core import health_get_goals
def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(health_get_goals(args))
    body = result if isinstance(result, str) else json.dumps(result, default=_json_default)
    return {"statusCode": 200, "body": body}