import asyncio
import json

from .core import analyze_rpe_drift


def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(analyze_rpe_drift(args))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}