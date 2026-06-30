import asyncio
import hashlib
import json
import os
import time as _time
from datetime import date, datetime, timedelta


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


def _get_federation_store():
    from federation_store import FederationStore
    return FederationStore(
        os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
        pk=os.environ.get("HEALTH_PROGRAM_PK", "operator"),
        region=os.environ.get("AWS_REGION", "ca-central-1"),
    )


def _floats_to_decimals(obj):
    from decimal import Decimal
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _floats_to_decimals(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_floats_to_decimals(v) for v in obj]
    return obj


def program_evaluation(args):
    import boto3
    from .config import AWS_REGION, IF_HEALTH_TABLE_NAME
    from .program_evaluation_ai import generate_program_evaluation_report

    refresh = args.get("refresh", False)
    cache_only = args.get("cache_only", False)

    store = _get_store()
    store.invalidate_cache()
    program = _run_async(store.get_program())
    federation_library = _run_async(_get_federation_store().get_library())
    active_pk = store.pk
    sessions = [s for s in program.get("sessions", []) if (s.get("block") or "current") == "current"]

    completed_weeks = sorted({
        int(s.get("week_number"))
        for s in sessions
        if (s.get("completed") or s.get("status") in ("logged", "completed")) and s.get("week_number") is not None
    })
    if len(completed_weeks) < 4:
        return {
            "insufficient_data": True,
            "insufficient_data_reason": "At least 4 completed weeks are required for a useful full-block evaluation.",
            "cached": False,
            "generated_at": "",
            "window_start": "",
            "weeks": len(completed_weeks),
        }

    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    window_start = week_start.isoformat()
    notes_fingerprint = hashlib.sha1(
        json.dumps(program.get("meta", {}).get("block_notes", []), sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:12]
    cache_sk = f"program_eval#{window_start}#{notes_fingerprint}"

    table = boto3.resource("dynamodb", region_name=AWS_REGION).Table(IF_HEALTH_TABLE_NAME)

    if not refresh:
        cached = table.get_item(Key={"pk": active_pk, "sk": cache_sk}).get("Item")
        if cached and cached.get("report"):
            report = cached["report"]
            if isinstance(report, dict):
                report["cached"] = True
                report["generated_at"] = cached.get("generated_at", "")
                report["window_start"] = window_start
                report["weeks"] = len(completed_weeks)
                return report

    if cache_only:
        return {
            "insufficient_data": True,
            "insufficient_data_reason": "No cached program evaluation exists. Generate it to run AI analysis.",
            "cache_miss": True,
            "cached": False,
            "generated_at": "",
            "window_start": window_start,
            "weeks": len(completed_weeks),
        }

    report = _run_async(generate_program_evaluation_report(program, federation_library=federation_library))
    generated_at = datetime.utcnow().isoformat() + "Z"
    report["cached"] = False
    report["generated_at"] = generated_at
    report["window_start"] = window_start
    report["weeks"] = len(completed_weeks)

    if not (report.get("insufficient_data") and str(report.get("insufficient_data_reason", "")).startswith("AI evaluation failed")):
        table.put_item(Item=_floats_to_decimals({
            "pk": active_pk,
            "sk": cache_sk,
            "report": report,
            "generated_at": generated_at,
            "window_start": window_start,
            "weeks": len(completed_weeks),
            "expires_at": int(_time.time()) + 7 * 86400,
        }))

    return report


def handler(event, context):
    args = event.get("args", event)
    result = program_evaluation(args)
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}