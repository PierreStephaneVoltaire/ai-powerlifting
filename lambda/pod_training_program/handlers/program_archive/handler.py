import asyncio
import json
from .core import program_archive

def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(program_archive(args))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}
