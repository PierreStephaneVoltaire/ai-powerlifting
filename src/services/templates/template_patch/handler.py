import json

from .core import template_patch


def handler(event, context):
    args = event.get("args", event)
    return {"statusCode": 200, "body": json.dumps(template_patch(args), default=str)}
