import asyncio, json
from .core import template_apply
def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(template_apply(args["sk"], args.get("target","new_block"), args.get("start_date"), args.get("week_start_day"), args.get("_person_pk") or args.get("actor_pk"), args.get("block_id"), args.get("block_name"), args.get("expected_revision"), args.get("idempotency_key"), args.get("pk")))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}
