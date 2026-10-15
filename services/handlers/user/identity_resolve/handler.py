import asyncio
import json
from decimal import Decimal

from .core import identity_resolve


def handler(event, context):
    result = asyncio.run(identity_resolve(event.get("args", event)))
    return {"statusCode": 200, "body": json.dumps(result, default=lambda value: float(value) if isinstance(value, Decimal) else str(value))}
