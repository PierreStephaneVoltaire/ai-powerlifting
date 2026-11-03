import json
from decimal import Decimal

from .core import ipf_weight_classes


def _json_default(obj):
    if isinstance(obj, Decimal):
        return float(obj) if obj % 1 > 0 else int(obj)
    return str(obj)


def handler(event, context):
    args = event.get("args", event)
    result = ipf_weight_classes(args["sex"])
    if isinstance(result, str):
        body = result
    else:
        body = json.dumps(result, default=_json_default)
    return {"statusCode": 200, "body": body}
