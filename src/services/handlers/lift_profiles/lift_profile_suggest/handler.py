import json

from .core import lift_profile_suggest


def handler(event, context):
    args = event.get("args", event)
    return {"statusCode": 200, "body": json.dumps(lift_profile_suggest(args), default=str)}
