import asyncio
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


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


def _get_federation_store():
    from federation_store import FederationStore
    return FederationStore(
        os.environ.get("IF_HEALTH_TABLE_NAME", "if-health"),
        pk=os.environ.get("HEALTH_PROGRAM_PK", "operator"),
        region=os.environ.get("AWS_REGION", "ca-central-1"),
    )


def block_program_evaluation(args):
    from .program_evaluation_ai import generate_program_evaluation_report

    program = args.get("program")
    if not isinstance(program, dict):
        return {
            "insufficient_data": True,
            "insufficient_data_reason": "A block-scoped program snapshot is required.",
            "cached": False,
            "generated_at": "",
            "window_start": "",
            "weeks": 0,
        }

    federation_library = None
    try:
        federation_library = args.get("_report_source", {}).get("federation_library") or _run_async(_get_federation_store().get_library())
    except Exception as exc:
        logger.warning("block_program_evaluation: federation library unavailable: %s", exc)

    report = _run_async(generate_program_evaluation_report(
        program,
        federation_library=federation_library,
    ))

    sessions = program.get("sessions", [])
    completed = [session for session in sessions if session.get("completed") or session.get("status") in {"logged", "completed"}]
    report.update(cached=False, generated_at=datetime.now(timezone.utc).isoformat(),
                  window_start=args.get("window_start") or min((session.get("date", "") for session in sessions if session.get("date")), default=""),
                  weeks=args.get("weeks") or len({session.get("week_number") for session in completed if session.get("week_number")}))
    return report
