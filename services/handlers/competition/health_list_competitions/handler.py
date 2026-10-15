import asyncio
import json
from decimal import Decimal

from .core import CompetitionConflictError, health_list_competitions



def _json_default(obj):
    if isinstance(obj, Decimal):
        return float(obj) if obj % 1 > 0 else int(obj)
    return str(obj)

def handler(event, context):
    args = event.get("args", event) or {}
    try:
        result = asyncio.run(health_list_competitions(args))
        body = result if isinstance(result, str) else json.dumps(result, default=_json_default)
        return {"statusCode": 200, "body": body}
    except CompetitionConflictError as exc:
        return {
            "statusCode": 409,
            "body": json.dumps({
                "code": "conflict",
                "message": str(exc),
                "current_revision": exc.current_revision,
                "current_record": exc.current_record,
            }, default=_json_default),
        }
