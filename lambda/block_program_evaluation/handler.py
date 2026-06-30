import asyncio
import json
import logging
import os

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
        federation_library = _run_async(_get_federation_store().get_library())
    except Exception as exc:
        logger.warning("block_program_evaluation: federation library unavailable: %s", exc)

    return _run_async(generate_program_evaluation_report(
        program,
        federation_library=federation_library,
    ))


def handler(event, context):
    args = event.get("args", event)
    result = block_program_evaluation(args)
    body = result if isinstance(result, str) else json.dumps(result, default=str)
    return {"statusCode": 200, "body": body}