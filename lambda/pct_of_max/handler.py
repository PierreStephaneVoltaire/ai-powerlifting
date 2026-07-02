import json

from .core import pct_of_max


def handler(event, context):
    args = event.get("args", event)
    result = pct_of_max(args["max_kg"], args["pct"])
    if isinstance(result, str):
        body = result
    else:
        body = json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}
