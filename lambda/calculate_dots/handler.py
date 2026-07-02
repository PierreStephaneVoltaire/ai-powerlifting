import json

from .core import calculate_dots


def handler(event, context):
    args = event.get("args", event)
    result = {"dots": calculate_dots(args["total_kg"], args["bodyweight_kg"], args["sex"])}
    if isinstance(result, str):
        body = result
    else:
        body = json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}