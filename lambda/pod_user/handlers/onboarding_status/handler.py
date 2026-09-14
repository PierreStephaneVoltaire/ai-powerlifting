import asyncio
import json

from .core import onboarding_status


def handler(event, context):
    result = asyncio.run(onboarding_status(event.get("args", event)))
    return {"statusCode": 200, "body": json.dumps(result)}
