import asyncio
import json

from .core import (
    load_data,
    filter_dataset,
    analyze_stats,
    DatasetNotReadyError,
)


async def _run(args):
    try:
        df = load_data()
    except DatasetNotReadyError as e:
        return f"ERROR: Dataset not ready. {str(e)}"
    except FileNotFoundError as e:
        return f"ERROR: Dataset missing. {str(e)}"

    filtered_df = filter_dataset(
        df,
        federation=args.get("federation"),
        country=args.get("country"),
        region=args.get("region"),
        equipment=args.get("equipment"),
        sex=args.get("sex"),
        age_class=args.get("age_class"),
        year=args.get("year"),
        event_type=args.get("event_type"),
        min_dots=args.get("min_dots"),
    )
    return analyze_stats(
        filtered_df,
        squat_kg=args.get("squat_kg"),
        bench_kg=args.get("bench_kg"),
        deadlift_kg=args.get("deadlift_kg"),
        bodyweight_kg=args.get("bodyweight_kg"),
        sex_code=args.get("sex_code"),
    )


def handler(event, context):
    args = event.get("args", event)
    result = asyncio.run(_run(args))
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}