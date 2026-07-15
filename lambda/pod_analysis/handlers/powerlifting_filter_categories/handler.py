import asyncio
import json
from decimal import Decimal

from .core import load_data, get_filter_categories, DatasetNotReadyError


async def _run(args):
    try:
        df = load_data()
        return get_filter_categories(df)
    except DatasetNotReadyError as e:
        return f"ERROR: Dataset not ready. {str(e)}"
    except FileNotFoundError as e:
        return f"ERROR: Dataset missing. {str(e)}"



def _json_default(obj):
    if isinstance(obj, Decimal):
        return float(obj) if obj % 1 > 0 else int(obj)
    return str(obj)

def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(_run(args))
    body = result if isinstance(result, str) else json.dumps(result, default=_json_default)
    return {"statusCode": 200, "body": body}