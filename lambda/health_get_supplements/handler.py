import asyncio
import json
from decimal import Decimal
from .core import health_get_supplements
def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(health_get_supplements(args))
    body = result if isinstance(result, str) else json.dumps(result, default=_json_default)
    return {"statusCode": 200, "body": body}