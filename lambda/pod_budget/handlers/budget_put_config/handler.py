import asyncio
import json
from decimal import Decimal

from .core import budget_put_config



def _json_default(obj):
    if isinstance(obj, Decimal):
        return float(obj) if obj % 1 > 0 else int(obj)
    return str(obj)

def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(budget_put_config(args))
    body = result if isinstance(result, str) else json.dumps(result, default=_json_default)
    return {"statusCode": 200, "body": body}