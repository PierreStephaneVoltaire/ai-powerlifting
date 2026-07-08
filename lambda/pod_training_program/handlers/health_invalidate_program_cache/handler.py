import json
from decimal import Decimal
from .core import health_invalidate_program_cache
def handler(event, context):
    args = event.get("args", event)
    result = health_invalidate_program_cache(args)
    body = result if isinstance(result, str) else json.dumps(result, default=_json_default)
    return {"statusCode": 200, "body": body}
