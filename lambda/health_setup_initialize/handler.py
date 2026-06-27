import asyncio
import json

from .core import health_setup_initialize


def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(
        health_setup_initialize(
            args["mode"],
            args["start_date"],
            args["week_start_day"],
            args.get("program_name"),
            args.get("template_sk"),
            args.get("maxes"),
        )
    )
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}