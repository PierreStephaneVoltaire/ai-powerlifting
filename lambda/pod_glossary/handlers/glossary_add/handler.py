import asyncio
import json
from decimal import Decimal

from .core import glossary_add



def _json_default(obj):
    if isinstance(obj, Decimal):
        return float(obj) if obj % 1 > 0 else int(obj)
    return str(obj)

def handler(event, context):
    args = event.get("args", event)
    exercise = args.get("term", args.get("exercise"))
    if not isinstance(exercise, dict) or not exercise:
        raise ValueError("term is required")
    result = asyncio.run(glossary_add(exercise, args.get("pk")))
    body = result if isinstance(result, str) else json.dumps(result, default=_json_default)
    return {"statusCode": 200, "body": body}
