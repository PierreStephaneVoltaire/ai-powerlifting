import asyncio
import json
from datetime import datetime


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


def block_correlation_analysis(args):
    from .correlation_ai import generate_correlation_report

    program = args.get("program")
    sessions = args.get("sessions")
    weeks = args.get("weeks", 4)
    window_start = args.get("window_start", "")
    if not isinstance(program, dict) or not isinstance(sessions, list):
        return {
            "findings": [],
            "summary": "",
            "generated_at": "",
            "window_start": window_start,
            "weeks": weeks,
            "cached": False,
            "insufficient_data": True,
            "insufficient_data_reason": "A block-scoped program and sessions snapshot is required.",
        }

    report = _run_async(generate_correlation_report(
        sessions=sessions,
        lift_profiles=program.get("lift_profiles", []),
        weeks=weeks,
        window_start=window_start,
        program=program,
    ))
    if isinstance(report, dict):
        report["cached"] = False
        report["generated_at"] = datetime.utcnow().isoformat() + "Z"
        report["window_start"] = window_start
        report["weeks"] = weeks
    return report


def handler(event, context):
    args = event.get("args", event)
    result = block_correlation_analysis(args)
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}