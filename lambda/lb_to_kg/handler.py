import json

from .core import lb_to_kg


def handler(event, context):
    args = event.get("args", event)
    result = lb_to_kg(args["lb"])
    if isinstance(result, str):
        body = result
    else:
        body = json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}