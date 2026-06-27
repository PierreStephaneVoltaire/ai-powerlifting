import asyncio
import json

from .core import health_create_session


def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(
        health_create_session(
            args["date"],
            args["day"],
            args["week_number"],
            args.get("exercises"),
            args.get("session_notes", ""),
        )
    )
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}