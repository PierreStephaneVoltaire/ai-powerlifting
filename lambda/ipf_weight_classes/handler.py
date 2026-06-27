import json

from .core import ipf_weight_classes


def handler(event, context):
    args = event.get("args", event)
    result = ipf_weight_classes(args["sex"])
    if isinstance(result, str):
        body = result
    else:
        body = json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}