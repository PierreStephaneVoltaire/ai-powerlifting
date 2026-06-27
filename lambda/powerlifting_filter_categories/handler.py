import asyncio
import json

from .core import load_data, get_filter_categories, DatasetNotReadyError


async def _run(args):
    try:
        df = load_data()
        return get_filter_categories(df)
    except DatasetNotReadyError as e:
        return f"ERROR: Dataset not ready. {str(e)}"
    except FileNotFoundError as e:
        return f"ERROR: Dataset missing. {str(e)}"


def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(_run(args))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}