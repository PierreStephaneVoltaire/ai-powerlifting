import asyncio
import json

from .core import glossary_add


def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(glossary_add(args["exercise"]))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}