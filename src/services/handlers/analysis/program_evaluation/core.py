import asyncio
import os
from datetime import date, datetime, timedelta
from services.lib.block_scope import scope_program


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


def _get_federation_store():
    from ....pod_federation.handlers._federation_store import FederationStore
    return FederationStore(
        os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
        pk=os.environ.get("HEALTH_PROGRAM_PK", "operator"),
        region=os.environ.get("AWS_REGION", "ca-central-1"),
    )


def program_evaluation(args):
    from .program_evaluation_ai import generate_program_evaluation_report

    store = _get_store()
    store.invalidate_cache()
    source = args.get("_report_source", {})
    from services.lib.competition_entries import with_competition_entries
    program = source["program"] if "program" in source else with_competition_entries(_run_async(store.get_program()), store.pk)
    federation_library = source["federation_library"] if "federation_library" in source else _run_async(_get_federation_store().get_library())
    sessions = scope_program(program).get("sessions", [])

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
    report = _run_async(generate_program_evaluation_report(program, federation_library=federation_library))
    report["cached"] = False
    report["generated_at"] = datetime.utcnow().isoformat() + "Z"
    report["window_start"] = (today - timedelta(days=today.weekday())).isoformat()
    report["weeks"] = len(completed_weeks)
    return report
