import asyncio
import json
from decimal import Decimal

from .core import glossary_update



def _json_default(obj):
    if isinstance(obj, Decimal):
        return float(obj) if obj % 1 > 0 else int(obj)
    return str(obj)

def handler(event, context):
    args = event.get("args", event)
    exercise_id = args.get("id")
    fields = args.get("fields", args.get("term"))
    if not exercise_id or not isinstance(fields, dict) or not fields:
        raise ValueError("id and fields are required")
    result = asyncio.run(glossary_update(exercise_id, fields, args.get("pk")))
    body = result if isinstance(result, str) else json.dumps(result, default=_json_default)
    return {"statusCode": 200, "body": body}
