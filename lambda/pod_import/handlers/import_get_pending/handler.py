import asyncio, json
from .core import import_get_pending
def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(import_get_pending(args["import_id"]))
    body = result if isinstance(result, str) else json.dumps(result, default=_json_default)
    return {"statusCode": 200, "body": body}
