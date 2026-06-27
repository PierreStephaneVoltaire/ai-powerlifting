import json
from .core import health_invalidate_program_cache
def handler(event, context):
    args = event.get("args", event)
    result = health_invalidate_program_cache()
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}
