import asyncio
import json

from .core import health_update_federation_library


def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(
        health_update_federation_library(
            {
                "federations": args["federations"],
                "qualification_standards": args["qualification_standards"],
            }
        )
    )
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}