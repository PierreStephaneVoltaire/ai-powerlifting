import asyncio, json
from .core import import_reject
def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(import_reject(args["import_id"], args.get("reason")))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}
