import asyncio
import json
from decimal import Decimal

from .core import calculate_attempts



def _json_default(obj):
    if isinstance(obj, Decimal):
        return float(obj) if obj % 1 > 0 else int(obj)
    return str(obj)

def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(
        calculate_attempts(
            args["lift"],
            args["opener_kg"],
            args.get("j1_override"),
            args.get("j2_override"),
            args.get("last_felt"),
        )
    )
    body = result if isinstance(result, str) else json.dumps(result, default=_json_default)
    return {"statusCode": 200, "body": body}