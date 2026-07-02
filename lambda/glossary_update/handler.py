import asyncio
import json

from .core import glossary_update


def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(glossary_update(args["id"], args["fields"]))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}