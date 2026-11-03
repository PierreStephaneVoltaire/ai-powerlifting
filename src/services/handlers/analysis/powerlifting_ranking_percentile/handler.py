import asyncio
import json
from decimal import Decimal

from .core import load_data, compute_ranking_percentiles, DatasetNotReadyError


async def _run(args):
    try:
        df = load_data()
    except DatasetNotReadyError as e:
        return f"ERROR: Dataset not ready. {str(e)}"
    except FileNotFoundError as e:
        return f"ERROR: Dataset missing. {str(e)}"

    return compute_ranking_percentiles(
        df,
        squat_kg=args.get("squat_kg"),
        bench_kg=args.get("bench_kg"),
        deadlift_kg=args.get("deadlift_kg"),
        bodyweight_kg=args.get("bodyweight_kg"),
        sex_code=args.get("sex_code"),
        country=args.get("country"),
        region=args.get("region"),
        age_class=args.get("age_class"),
        equipment=args.get("equipment"),
    )



def _json_default(obj):
    if isinstance(obj, Decimal):
        return float(obj) if obj % 1 > 0 else int(obj)
    return str(obj)

def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(_run(args))
    body = result if isinstance(result, str) else json.dumps(result, default=_json_default)
    return {"statusCode": 200, "body": body}