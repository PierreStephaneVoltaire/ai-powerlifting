import asyncio, json
from .core import template_create_from_payload
def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(template_create_from_payload(args["template"], args.get("actor_pk") or args.get("pk"), args.get("author"), args.get("published", False), args.get("import_job_id")))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}
