import asyncio
import os
from datetime import datetime, timedelta


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
    from services.lib.program_store import ProgramStore
    return ProgramStore(
        table_name=os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
        pk=os.environ.get("HEALTH_PROGRAM_PK", "operator"),
        region=os.environ.get("AWS_REGION", "ca-central-1"),
    )


def correlation_analysis(args):
    from .correlation_ai import generate_correlation_report

    weeks = args.get("weeks", 4)
    today = datetime.utcnow().date()
    raw_cutoff = today - timedelta(weeks=weeks)
    window_start_str = (raw_cutoff - timedelta(days=raw_cutoff.weekday())).isoformat()

    store = _get_store()
    store.invalidate_cache()
    source = args.get("_report_source", {})
    from services.lib.competition_entries import with_competition_entries
    program = source["program"] if "program" in source else with_competition_entries(_run_async(store.get_program()), store.pk)

    report = _run_async(generate_correlation_report(
        sessions=program.get("sessions", []),
        lift_profiles=program.get("lift_profiles", []),
        weeks=weeks,
        window_start=window_start_str,
        program=program,
    ))
    report["cached"] = False
    report["generated_at"] = datetime.utcnow().isoformat() + "Z"
    report["window_start"] = window_start_str
    report["weeks"] = weeks
    return report
