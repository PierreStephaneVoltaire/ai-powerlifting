import asyncio, json
from .core import template_get
def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(template_get(args["sk"], args.get("_person_pk") or args.get("actor_pk")))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}
