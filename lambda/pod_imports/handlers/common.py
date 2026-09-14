import json
from decimal import Decimal


def json_default(value):
    if isinstance(value, Decimal):
        return float(value) if value % 1 else int(value)
    return str(value)


def arguments(event):
    return event.get("args", event)


def response(value):
    return {"statusCode": 200, "body": json.dumps(value, default=json_default)}
