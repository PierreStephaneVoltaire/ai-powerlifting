import asyncio, json
from .core import template_update
def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(template_update(args["sk"], args["template"], args.get("actor_pk") or args.get("pk")))
    body = result if isinstance(result, str) else json.dumps(result, default=_json_default)
    return {"statusCode": 200, "body": body}
