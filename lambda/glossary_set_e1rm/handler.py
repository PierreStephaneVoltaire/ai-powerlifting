import asyncio
import json

from .core import glossary_set_e1rm


def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(glossary_set_e1rm(args["id"], args["value_kg"], args.get("method", "manual")))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}