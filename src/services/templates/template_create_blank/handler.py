import asyncio, json
from .core import template_create_blank
def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(template_create_blank(
        args["name"],
        description=args.get("description", ""),
        estimated_weeks=args.get("estimated_weeks", 4),
        days_per_week=args.get("days_per_week", 3),
        actor_pk=args.get("_person_pk") or args.get("actor_pk"),
        author=args.get("author"),
        program_context=args.get("program_context", ""),
    ))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}
