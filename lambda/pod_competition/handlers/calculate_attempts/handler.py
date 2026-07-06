import asyncio
import json

from .core import calculate_attempts


def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(
        calculate_attempts(
            args["lift"],
            args["opener_kg"],
            args.get("j1_override"),
            args.get("j2_override"),
            args.get("last_felt"),
        )
    )
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}