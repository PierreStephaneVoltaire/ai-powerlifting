import json

from .core import estimate_1rm


def handler(event, context):
    args = event.get("args", event)
    result = estimate_1rm(args["weight_kg"], args["reps"], args.get("rpe"))
    if isinstance(result, str):
        body = result
    else:
        body = json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}