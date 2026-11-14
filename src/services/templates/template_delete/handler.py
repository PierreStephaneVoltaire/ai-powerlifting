import asyncio
import json

from .core import template_delete


def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(template_delete(args["sk"], args.get("_person_pk") or args.get("actor_pk")))
    return {"statusCode": 200, "body": json.dumps(result, default=str)}
