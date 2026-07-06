import asyncio, json
from .core import template_create_from_block
def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(template_create_from_block(args["name"], args.get("program_sk"), args.get("actor_pk") or args.get("pk"), args.get("author")))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}
