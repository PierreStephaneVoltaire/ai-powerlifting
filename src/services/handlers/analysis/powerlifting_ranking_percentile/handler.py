import asyncio
import hashlib
import json
from datetime import date
from decimal import Decimal

from services.lib import opl_dataset, valkey
from .core import load_data, compute_ranking_percentiles, DatasetNotReadyError

_RANKING_INPUTS = ("squat_kg", "bench_kg", "deadlift_kg", "bodyweight_kg", "sex_code", "country", "region", "age_class", "equipment")


def _cache_key(args) -> str:
    inputs = json.dumps({name: args.get(name) for name in _RANKING_INPUTS}, sort_keys=True, default=_json_default)
    digest = hashlib.sha256(inputs.encode()).hexdigest()
    return f"pl:rankings:{opl_dataset.identity()}:{date.today().year}:{args.get('pk', '')}:{digest}"


async def _run(args):
    try:
        df = load_data()
    except DatasetNotReadyError as e:
        return f"ERROR: Dataset not ready. {str(e)}"
    except FileNotFoundError as e:
        return f"ERROR: Dataset missing. {str(e)}"

    key = _cache_key(args)
    cached = valkey.get_json(key)
    if cached is not None:
        return cached
    result = compute_ranking_percentiles(
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
    valkey.set_json(key, result)
    return result



def _json_default(obj):
    if isinstance(obj, Decimal):
        return float(obj) if obj % 1 > 0 else int(obj)
    return str(obj)

def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(_run(args))
    body = result if isinstance(result, str) else json.dumps(result, default=_json_default)
    return {"statusCode": 200, "body": body}