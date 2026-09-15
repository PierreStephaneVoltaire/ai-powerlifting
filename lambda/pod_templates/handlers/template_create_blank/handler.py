import asyncio, json
from .core import template_create_blank
def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(template_create_blank(args["name"], args.get("description", ""), args.get("estimated_weeks", 4), args.get("days_per_week", 3), args.get("_person_pk") or args.get("actor_pk"), args.get("author"), args.get("expected_revision"), args.get("idempotency_key")))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}
