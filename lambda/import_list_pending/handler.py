import asyncio, json
from .core import import_list_pending
def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(import_list_pending(args.get("import_type")))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}
