import asyncio
import json
import os
from datetime import datetime, timedelta
from decimal import Decimal


def _run_async(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


def _get_store():
    from program_store import ProgramStore
    return ProgramStore(
        table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
        pk=os.environ.get("HEALTH_PROGRAM_PK", "operator"),
        region=os.environ.get("AWS_REGION", "ca-central-1"),
    )


def _floats_to_decimals(obj):
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _floats_to_decimals(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_floats_to_decimals(v) for v in obj]
    return obj


def correlation_analysis(args):
    import boto3
    from .config import AWS_REGION, IF_HEALTH_TABLE_NAME
    from .correlation_ai import generate_correlation_report

    weeks = args.get("weeks", 4)
    refresh = args.get("refresh", False)
    cache_only = args.get("cache_only", False)

    today = datetime.utcnow().date()
    raw_cutoff = today - timedelta(weeks=weeks)
    days_since_monday = raw_cutoff.weekday()
    window_start = raw_cutoff - timedelta(days=days_since_monday)
    window_start_str = window_start.isoformat()
    cache_sk = f"corr_report#{window_start_str}_{weeks}w"

    store = _get_store()
    active_pk = store.pk
    table = boto3.resource("dynamodb", region_name=AWS_REGION).Table(IF_HEALTH_TABLE_NAME)

    if not refresh:
        cached = table.get_item(Key={"pk": active_pk, "sk": cache_sk}).get("Item")
        if cached and cached.get("report"):
            report = cached["report"]
            if isinstance(report, dict):
                report["cached"] = True
                report["generated_at"] = cached.get("generated_at", "")
                report["window_start"] = window_start_str
                report["weeks"] = weeks
            return report

    if cache_only:
        return {
            "findings": [],
            "summary": "",
            "insufficient_data": True,
            "insufficient_data_reason": "No cached ROI correlation report exists. Generate it to run AI analysis.",
            "cache_miss": True,
            "cached": False,
            "generated_at": "",
            "window_start": window_start_str,
            "weeks": weeks,
        }

    store.invalidate_cache()
    program = _run_async(store.get_program())
    sessions = program.get("sessions", [])
    lift_profiles = program.get("lift_profiles", [])

    report = _run_async(generate_correlation_report(
        sessions=sessions,
        lift_profiles=lift_profiles,
        weeks=weeks,
        window_start=window_start_str,
        program=program,
    ))

    generated_at = datetime.utcnow().isoformat() + "Z"
    table.put_item(Item=_floats_to_decimals({
        "pk": active_pk,
        "sk": cache_sk,
        "report": report,
        "generated_at": generated_at,
        "window_start": window_start_str,
        "weeks": weeks,
    }))

    report["cached"] = False
    report["generated_at"] = generated_at
    report["window_start"] = window_start_str
    report["weeks"] = weeks
    return report
