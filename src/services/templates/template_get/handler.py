import asyncio
import json
from decimal import Decimal

from .core import template_get


def _json_default(value):
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    return str(value)


def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(template_get(args["sk"], args.get("_person_pk") or args.get("actor_pk")))
    body = result if isinstance(result, str) else json.dumps(result, default=_json_default)
    return {"statusCode": 200, "body": body}
