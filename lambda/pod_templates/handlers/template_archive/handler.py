import asyncio, json
from .core import template_archive
def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(template_archive(args["sk"], args.get("actor_pk") or args.get("pk")))
    body = result if isinstance(result, str) else json.dumps(result, default=_json_default)
    return {"statusCode": 200, "body": body}
