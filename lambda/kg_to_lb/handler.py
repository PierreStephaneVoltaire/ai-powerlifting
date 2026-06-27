import json

from .core import kg_to_lb


def handler(event, context):
    args = event.get("args", event)
    result = kg_to_lb(args["kg"])
    if isinstance(result, str):
        body = result
    else:
        body = json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}