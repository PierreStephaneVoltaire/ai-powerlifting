import asyncio, json
from .core import template_create_from_payload
def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(template_create_from_payload(args["template"], args.get("_person_pk") or args.get("actor_pk"), args.get("author"), args.get("published", False), args.get("import_job_id"), args.get("expected_revision"), args.get("idempotency_key")))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}
