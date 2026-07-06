import asyncio, json
from .core import template_unpublish
def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(template_unpublish(args["sk"], args.get("actor_pk") or args.get("pk")))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}
