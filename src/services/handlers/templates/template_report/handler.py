import json

from .core import template_report


def handler(event, context):
    args = event.get("args", event)
    return {"statusCode": 200, "body": json.dumps(template_report(args), default=str)}
