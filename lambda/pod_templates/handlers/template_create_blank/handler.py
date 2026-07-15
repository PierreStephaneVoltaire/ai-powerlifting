import asyncio, json
from .core import template_create_blank
def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(template_create_blank(args["name"], args.get("description", ""), args.get("estimated_weeks", 4), args.get("days_per_week", 3), args.get("actor_pk") or args.get("pk"), args.get("author")))
    body = result if isinstance(result, str) else json.dumps(result, default=_json_default)
    return {"statusCode": 200, "body": body}
