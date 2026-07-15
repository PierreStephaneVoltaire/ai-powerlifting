import asyncio, json
from .core import template_copy
def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(template_copy(args["sk"], args["new_name"], args.get("actor_pk") or args.get("pk"), args.get("author")))
    body = result if isinstance(result, str) else json.dumps(result, default=_json_default)
    return {"statusCode": 200, "body": body}
