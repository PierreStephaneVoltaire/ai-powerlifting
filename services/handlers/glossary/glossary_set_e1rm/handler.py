import asyncio
import json
from decimal import Decimal

from .core import glossary_set_e1rm



def _json_default(obj):
    if isinstance(obj, Decimal):
        return float(obj) if obj % 1 > 0 else int(obj)
    return str(obj)

def handler(event, context):
    args = event.get("args", event)
    if not args.get("id") or not isinstance(args.get("value_kg"), (int, float)) or isinstance(args.get("value_kg"), bool):
        raise ValueError("id and value_kg are required")
    result = asyncio.run(glossary_set_e1rm(args["id"], args["value_kg"], args.get("method", "manual"), args.get("pk")))
    body = result if isinstance(result, str) else json.dumps(result, default=_json_default)
    return {"statusCode": 200, "body": body}
